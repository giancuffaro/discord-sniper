"""Provider fallback for the observation-only reader and for screenshot reads.

Neither path ever sends an order. Both return a PROPOSED read that the normal
parser and guards then judge — AI confidence alone never authorizes an order.
"""
import json
import time
import threading
import requests
import ai_reader

DEFAULT_MODELS = {'openai': 'gpt-5.4', 'gemini': 'gemini-3.1-flash-lite'}
DEFAULT_ORDER = ('openai', 'gemini')
# THE LIVE READER LANES (9/14) — the one-message text reader and the screenshot
# reader. Same two providers, same keys, same cooldowns as the observer; their
# own order setting only so the live lanes can be steered without moving the
# measurement observer. They exist because BOTH lanes still hard-coded
# Anthropic, which has been billing-blocked since 9/13: on 9/14 that was 242
# "AI READ no call - ai: HTTP 400" lines and every screenshot read of the day.
DEFAULT_READER_ORDER = ('openai', 'gemini')
_cooldown = {}
_lock = threading.Lock()


def available(cfg):
    settings = cfg.get('context_observer') or {}
    keys = cfg.get('ai_provider_keys') or {}
    return bool(settings.get('enabled') and any(keys.get(p) for p in ('openai', 'gemini')))


def providers_available(cfg):
    """A live lane can read as soon as ONE provider key exists. Deliberately not
    gated on context_observer.enabled: that switch governs the measurement
    observer, and turning measurement off must never blind the live readers."""
    keys = (cfg or {}).get('ai_provider_keys') or {}
    return any(keys.get(p) for p in DEFAULT_READER_ORDER)


def request(provider, model, key, system, prompt, output_limit=1600, reasoning="low", timeout_seconds=30, images=None):
    """One call to one provider. `images` is [(media_type, base64), ...] for a
    screenshot read and None for text; everything else is identical, so the two
    lanes cannot drift apart."""
    if provider == 'openai':
        url = 'https://api.openai.com/v1/responses'
        headers = {'Authorization': 'Bearer ' + key}
        if images:
            content = [{'type': 'input_image',
                        'image_url': 'data:%s;base64,%s' % (mt, b64)}
                       for mt, b64 in images]
            content.append({'type': 'input_text', 'text': 'Return JSON.\n' + prompt})
            payload = [{'role': 'user', 'content': content}]
        else:
            payload = 'Return JSON.\n' + prompt
        body = {'model': model, 'instructions': system, 'input': payload,
                'max_output_tokens': output_limit, 'reasoning': {'effort': reasoning},
                'text': {'format': {'type': 'json_object'}}, 'store': False}
    else:
        url = 'https://generativelanguage.googleapis.com/v1beta/models/' + model + ':generateContent'
        headers = {'x-goog-api-key': key}
        parts = [{'inline_data': {'mime_type': mt, 'data': b64}}
                 for mt, b64 in (images or [])]
        parts.append({'text': prompt})
        body = {'systemInstruction': {'parts': [{'text': system}]},
                'contents': [{'parts': parts}],
                'generationConfig': {'maxOutputTokens': output_limit, 'responseMimeType': 'application/json'}}
    try:
        r = requests.post(url, headers=headers, json=body, timeout=(5, timeout_seconds), allow_redirects=False)
        if not 200 <= r.status_code < 300:
            return {'_error': 'HTTP_%d' % r.status_code}
        data = r.json()
        if provider == 'openai':
            text = ''.join(c.get('text', '') for item in data.get('output', [])
                           for c in item.get('content', []) if c.get('type') == 'output_text')
            complete = data.get('status') == 'completed'
            usage = data.get('usage', {})
        else:
            candidates = data.get('candidates', [])
            text = ''.join(p.get('text', '') for c in candidates for p in c.get('content', {}).get('parts', []))
            complete = bool(candidates) and candidates[0].get('finishReason') == 'STOP'
            usage = data.get('usageMetadata', {})
        raw = ai_reader._extract_json(text)
        if not complete or not isinstance(raw, dict):
            return {'_error': 'incomplete_or_invalid_json'}
        raw.update(_provider=provider, _model=model, _usage=usage)
        return raw
    except requests.Timeout:
        return {'_error': 'timeout'}
    except Exception:
        return {'_error': 'connection_or_response_error'}


def _order(settings, field, default):
    configured = (settings.get(field) or default)
    order = tuple(p for p in configured if p in default)
    if len(order) != len(default) or set(order) != set(default):
        order = default
    return order


def _run(system, prompt, cfg, order, images, output_limit):
    started = time.monotonic()
    settings = cfg.get('context_observer') or {}
    keys = cfg.get('ai_provider_keys') or {}
    models = (settings.get('vision_models') if images else settings.get('models')) or {}
    attempts = []
    for provider in order:
        key = keys.get(provider)
        model = models.get(provider) or DEFAULT_MODELS[provider]
        if not key:
            attempts.append({'provider': provider, 'error': 'missing_key'})
            continue
        with _lock:
            cooling = _cooldown.get((provider, model), 0) > time.monotonic()
        if cooling:
            attempts.append({'provider': provider, 'error': 'cooldown'})
            continue
        if images:
            result = request(provider, model, key, system, prompt,
                             output_limit=output_limit, images=images)
        else:
            result = request(provider, model, key, system, prompt)
        error = result.get('_error')
        attempts.append({'provider': provider, 'model': model, 'error': error})
        if not error:
            result['_attempts'] = attempts
            return result, round((time.monotonic() - started) * 1000)
        with _lock:
            # Avoid repeatedly charging/timeouting on an unavailable provider.
            _cooldown[(provider, model)] = time.monotonic() + (900 if error in ('HTTP_400','HTTP_401','HTTP_402','HTTP_403') else 60)
    return {'_error': 'all_providers_unavailable', '_attempts': attempts}, round((time.monotonic() - started) * 1000)


def read(system, prompt, cfg):
    settings = cfg.get('context_observer') or {}
    if not available(cfg):
        return {'_error': 'observer_disabled_or_missing_keys'}, 0
    return _run(system, prompt, cfg,
                _order(settings, 'provider_order', DEFAULT_ORDER), None, 1600)


def read_signal(system, prompt, cfg, output_limit=400):
    """ONE message read for the live reader lane. Same keys, same order and the
    same cooldown map as the observer — not gated on the observer's own switch,
    because measurement being off must never stop the live reader reading."""
    settings = cfg.get('context_observer') or {}
    if not providers_available(cfg):
        return {'_error': 'no_provider_key'}, 0
    return _run(system, prompt, cfg,
                _order(settings, 'reader_provider_order', DEFAULT_READER_ORDER),
                None, output_limit)


def read_image(system, prompt, images, cfg, output_limit=900):
    """A screenshot read, through the same keys, order and cooldowns as the
    text lanes. `images` is [(media_type, base64), ...]."""
    settings = cfg.get('context_observer') or {}
    if not providers_available(cfg):
        return {'_error': 'no_provider_key'}, 0
    if not images:
        return {'_error': 'no_image'}, 0
    return _run(system, prompt, cfg,
                _order(settings, 'reader_provider_order', DEFAULT_READER_ORDER),
                list(images), output_limit)
