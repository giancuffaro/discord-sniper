"""Provider fallback for the observation-only reader. Never sends orders."""
import json
import time
import threading
import requests
import ai_reader

DEFAULT_MODELS = {'openai': 'gpt-5.4', 'gemini': 'gemini-3.1-flash-lite'}
_cooldown = {}
_lock = threading.Lock()


def available(cfg):
    settings = cfg.get('context_observer') or {}
    keys = cfg.get('ai_provider_keys') or {}
    return bool(settings.get('enabled') and any(keys.get(p) for p in ('openai', 'gemini')))


def request(provider, model, key, system, prompt, output_limit=1600, reasoning="low", timeout_seconds=30):
    if provider == 'openai':
        url = 'https://api.openai.com/v1/responses'
        headers = {'Authorization': 'Bearer ' + key}
        body = {'model': model, 'instructions': system, 'input': 'Return JSON.\n' + prompt,
                'max_output_tokens': output_limit, 'reasoning': {'effort': reasoning},
                'text': {'format': {'type': 'json_object'}}, 'store': False}
    else:
        url = 'https://generativelanguage.googleapis.com/v1beta/models/' + model + ':generateContent'
        headers = {'x-goog-api-key': key}
        body = {'systemInstruction': {'parts': [{'text': system}]},
                'contents': [{'parts': [{'text': prompt}]}],
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


def read(system, prompt, cfg):
    started = time.monotonic()
    settings = cfg.get('context_observer') or {}
    keys = cfg.get('ai_provider_keys') or {}
    attempts = []
    if not available(cfg):
        return {'_error': 'observer_disabled_or_missing_keys'}, 0
    for provider in ('openai', 'gemini'):
        key = keys.get(provider)
        model = (settings.get('models') or {}).get(provider) or DEFAULT_MODELS[provider]
        if not key:
            attempts.append({'provider': provider, 'error': 'missing_key'})
            continue
        with _lock:
            cooling = _cooldown.get((provider, model), 0) > time.monotonic()
        if cooling:
            attempts.append({'provider': provider, 'error': 'cooldown'})
            continue
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
