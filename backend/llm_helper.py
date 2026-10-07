"""Offline LLM helper powered by Ollama.

Ollama runs a local model server (default http://localhost:11434) with a
REST API. This module wraps it for WAYOUT's survival-assistance use case.

Speed-oriented choices:
  - Default model is qwen2.5:1.5b: ~3x faster on CPU than gemma2:2b.
  - keep_alive holds the model in RAM between requests.
  - Streaming responses yield tokens to the client as they generate, so
    even a slow model shows progress within one second.
  - num_predict is capped at 200 tokens. Survival answers don't need more.
  - System prompt is trimmed. A long prompt costs prefill time on every call.

If Ollama is not running, callers get a clear "not available" response;
the frontend can then show a rule-based assistant instead.
"""
import json
import os

import requests

OLLAMA_URL = os.getenv('OLLAMA_URL', 'http://127.0.0.1:11434')
MODEL = os.getenv('OLLAMA_MODEL', 'qwen2.5:1.5b')

# Short system prompt = faster prefill = faster first token.
SYSTEM_PROMPT = """You are WAYOUT's assistant for disasters and everyday life.
Rules:
- Under 100 words unless asked for detail.
- Concrete actions, not general advice.
- If life-threatening: say "call emergency services" first.
- Never invent phone numbers or addresses.
- Plain language. No jargon.
- You may discuss first aid, shelter, water, fire, signalling, navigation,
  power, staying warm or cool, food safety, evacuation basics, and also
  respond helpfully to ordinary questions and casual conversation.
"""


def _headers():
    return {'Content-Type': 'application/json'}


def is_available():
    """Return True if Ollama responds to a basic ping."""
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


def _build_payload(question, context=None, model=None, stream=False):
    model = model or MODEL
    user_msg = (question or '').strip()
    if context:
        parts = []
        if context.get('lat') and context.get('lon'):
            try:
                parts.append(f"User location: {context['lat']:.4f}, {context['lon']:.4f}")
            except (TypeError, ValueError):
                pass
        if context.get('region'):
            parts.append(f"Region: {context['region']}")
        if context.get('hazard'):
            parts.append(f"Active hazard: {context['hazard']}")
        if context.get('scenario'):
            parts.append(
                f"SCENARIO (mock exercise): {context['scenario']}. "
                f"Answer as if the user is in this emergency. "
                f"Note it is a simulation outside this conversation."
            )
        if parts:
            user_msg = '\n'.join(parts) + '\n\nUser: ' + user_msg

    return {
        'model': model,
        'system': SYSTEM_PROMPT,
        'prompt': user_msg,
        'stream': stream,
        'keep_alive': '30m',
        'options': {
            'temperature': 0.4,
            'num_predict': 200,
            'num_ctx': 1024,
            'top_p': 0.9,
            'repeat_penalty': 1.1,
        },
    }


def ask(question, context=None, model=None, timeout=120):
    """Non-streaming ask. Returns {available, answer, model, error}."""
    model = model or MODEL
    if not is_available():
        return {
            'available': False,
            'answer': None,
            'model': model,
            'error': 'Local LLM is not running. Start it with: '
                     'ollama serve (and: ollama pull ' + model + ')',
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
        return {
            'available': True, 'answer': None, 'model': model,
            'error': 'The local model timed out. Try a shorter question '
                     'or restart Ollama.',
        }
    except Exception as exc:
        return {'available': True, 'answer': None, 'model': model,
                'error': str(exc)}


def stream(question, context=None, model=None):
    """Streaming ask. Yields plain string chunks as they generate.

    Yields nothing and raises RuntimeError if Ollama is unreachable. The
    caller (a Flask streaming response) is expected to catch this and
    send an error payload.
    """
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