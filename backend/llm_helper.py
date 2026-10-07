"""Offline LLM helper powered by Ollama.

Tuned for speed on CPU:
  - Default model qwen2.5:0.5b (~400 MB, ~40 tok/s on CPU)
  - keep_alive=-1 holds the model in RAM indefinitely
  - num_predict=110 caps response length
  - num_ctx=512 shrinks the KV cache so prefill is fast
  - Barebones system prompt = minimal prefill cost
  - warmup() preloads the model at Flask startup
"""
import json
import os

import requests

OLLAMA_URL = os.getenv('OLLAMA_URL', 'http://127.0.0.1:11434')
MODEL = os.getenv('OLLAMA_MODEL', 'qwen2.5:0.5b')

SYSTEM_PROMPT = """Survival assistant. Answer in under 80 words.
If life-threatening, say "call emergency services" first.
Concrete actions only. Plain language.
Topics: first aid, water, fire, shelter, warmth, navigation, disasters."""


def _headers():
    return {'Content-Type': 'application/json'}


def is_available():
    try:
        r = requests.get(f'{OLLAMA_URL}/api/tags', timeout=2)
        return r.status_code == 200
    except Exception:
        return False


def list_models():
    try:
        r = requests.get(f'{OLLAMA_URL}/api/tags', timeout=3)
        if r.status_code != 200:
            return []
        return [m.get('name') for m in r.json().get('models', [])]
    except Exception:
        return []


def warmup(model=None):
    """Load the model into RAM at startup so the first request is fast."""
    model = model or MODEL
    if not is_available():
        return False
    try:
        r = requests.post(
            f'{OLLAMA_URL}/api/generate',
            json={
                'model': model,
                'prompt': 'hi',
                'stream': False,
                'keep_alive': -1,
                'options': {'num_predict': 1, 'num_ctx': 128},
            },
            timeout=60,
        )
        return r.status_code == 200
    except Exception as exc:
        print(f'[llm] warmup failed: {exc}', flush=True)
        return False


def _build_payload(question, context=None, model=None, stream=False):
    model = model or MODEL
    user_msg = (question or '').strip()
    if context:
        parts = []
        if context.get('lat') and context.get('lon'):
            try:
                parts.append(f"at {context['lat']:.2f},{context['lon']:.2f}")
            except (TypeError, ValueError):
                pass
        if context.get('region'):
            parts.append(f"region {context['region']}")
        if context.get('hazard'):
            parts.append(f"hazard {context['hazard']}")
        if parts:
            user_msg = '[' + ', '.join(parts) + '] ' + user_msg

    return {
        'model': model,
        'system': SYSTEM_PROMPT,
        'prompt': user_msg,
        'stream': stream,
        'keep_alive': -1,
        'options': {
            'temperature': 0.5,
            'num_predict': 110,
            'num_ctx': 512,
            'top_p': 0.9,
            'repeat_penalty': 1.1,
            'num_thread': 4,
        },
    }


def ask(question, context=None, model=None, timeout=45):
    model = model or MODEL
    if not is_available():
        return {
            'available': False,
            'answer': None,
            'model': model,
            'error': 'Local LLM is not running.',
        }
    payload = _build_payload(question, context, model, stream=False)
    try:
        r = requests.post(f'{OLLAMA_URL}/api/generate',
                          json=payload, timeout=timeout)
        if r.status_code != 200:
            return {'available': True, 'answer': None, 'model': model,
                    'error': f'Ollama returned {r.status_code}'}
        data = r.json()
        return {
            'available': True,
            'answer': (data.get('response') or '').strip(),
            'model': model,
            'error': None,
        }
    except requests.exceptions.Timeout:
        return {'available': True, 'answer': None, 'model': model,
                'error': 'Model timed out. Try a shorter question.'}
    except Exception as exc:
        return {'available': True, 'answer': None, 'model': model,
                'error': str(exc)}


def stream(question, context=None, model=None):
    """Streaming ask. Yields chunks as they generate."""
    model = model or MODEL
    if not is_available():
        raise RuntimeError('Local LLM is not running.')
    payload = _build_payload(question, context, model, stream=True)
    try:
        with requests.post(f'{OLLAMA_URL}/api/generate',
                           json=payload, timeout=(10, 180),
                           stream=True) as r:
            if r.status_code != 200:
                raise RuntimeError(f'Ollama returned {r.status_code}')
            for line in r.iter_lines(decode_unicode=False):
                if not line:
                    continue
                try:
                    obj = json.loads(line.decode('utf-8'))
                except Exception:
                    continue
                chunk = obj.get('response')
                if chunk:
                    yield chunk
                if obj.get('done'):
                    break
    except requests.exceptions.Timeout:
        raise RuntimeError('The local model timed out.')