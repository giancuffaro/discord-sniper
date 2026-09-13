"""Explicit, one-shot provider probes. No secrets or response bodies are logged."""
import concurrent.futures
import json
import time
from datetime import datetime, timezone
from pathlib import Path
import requests

HERE = Path(__file__).resolve().parent


def probe(provider, key, model_override=None):
    models = {'openai':'gpt-4.1-2025-04-14','anthropic':'claude-haiku-4-5-20251001',
              'gemini':'gemini-3.1-flash-lite','perplexity':'sonar','deepseek':'deepseek-chat'}
    model = model_override or models[provider]
    result = {'provider':provider,'model':model,'checked_at':datetime.now(timezone.utc).isoformat()}
    if not key:
        return dict(result,status='missing_key')
    headers = {'Content-Type':'application/json'}
    prompt = 'Reply with exactly OK.'
    if provider == 'gemini':
        url = 'https://generativelanguage.googleapis.com/v1beta/models/'+model+':generateContent'
        headers['x-goog-api-key'] = key
        body = {'contents':[{'parts':[{'text':prompt}]}],'generationConfig':{'maxOutputTokens':16}}
    elif provider == 'anthropic':
        url = 'https://api.anthropic.com/v1/messages'
        headers.update({'x-api-key':key,'anthropic-version':'2023-06-01'})
        body = {'model':model,'max_tokens':16,'messages':[{'role':'user','content':prompt}]}
    else:
        url = {'openai':'https://api.openai.com/v1/chat/completions',
               'perplexity':'https://api.perplexity.ai/v1/sonar',
               'deepseek':'https://api.deepseek.com/chat/completions'}[provider]
        headers['Authorization']='Bearer '+key
        body={'model':model,'max_tokens':16,'messages':[{'role':'user','content':prompt}]}
    started=time.monotonic()
    try:
        response=requests.post(url,headers=headers,json=body,timeout=(5,35),allow_redirects=False)
        result['http_status']=response.status_code
        try: data=response.json()
        except ValueError: data={}
        # Error content used for classification only, never stored or printed.
        detail=json.dumps(data.get('error',{})).lower() if isinstance(data,dict) else ''
        code=response.status_code
        if 200 <= code < 300:
            if provider=='gemini':
                output=''.join(p.get('text','') for c in data.get('candidates',[]) for p in c.get('content',{}).get('parts',[]))
            elif provider=='anthropic':
                output=''.join(p.get('text','') for p in data.get('content',[]))
            else:
                output=''.join(c.get('message',{}).get('content') or '' for c in data.get('choices',[]))
            state='working' if output.strip() else 'accepted_without_text'
            result['expected_reply']=output.strip().strip('.!').upper()=='OK'
        elif code==401 or 'api_key_invalid' in detail or 'api key not valid' in detail:
            state='authentication_rejected'
        elif code==402 or any(x in detail for x in ('insufficient_quota','insufficient balance','credit balance','insufficient credit','billing')):
            state='billing_or_credits'
        elif code==429: state='quota_or_rate_limit'
        elif code==403: state='access_denied'
        elif code==404: state='model_or_endpoint_unavailable'
        elif code>=500: state='provider_unavailable'
        else: state='request_rejected'
        result['status']=state
    except requests.Timeout: result['status']='timeout'
    except Exception: result['status']='connection_or_response_error'
    result['latency_ms']=round((time.monotonic()-started)*1000)
    return result


def main():
    cfg=json.loads((HERE/'settings.json').read_text(encoding='utf-8'))
    keys=dict(cfg.get('ai_provider_keys') or {})
    keys['anthropic']=cfg.get('execution',{}).get('ai_reader',{}).get('api_key','')
    providers=('openai','anthropic','gemini','perplexity','deepseek')
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        results=list(pool.map(lambda p:probe(p,str(keys.get(p) or '').strip()),providers))
    out=HERE/'local-reader-measure'/'provider-key-check.json'
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(results,indent=2),encoding='utf-8')
    print(json.dumps(results,indent=2))


if __name__=='__main__': main()
