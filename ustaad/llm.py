"""
The brains that write Ustaad's answers.
  Default order:  Sarvam-105B writes  ->  Groq (gpt-oss-120b) is the backup  ->  rules, if no key at all.
  WRITER=groq in the settings swaps Sarvam and Groq.
  Bring your own brain: set BRAIN_URL / BRAIN_KEY / BRAIN_MODEL and that AI writes first (OpenAI, Gemini, Claude,
  or a company's own model) — memory, maths, voice and translation stay exactly the same.
Also here: Groq Whisper (last-resort ears), Groq vision (photo backup), Sarvam Bulbul (voice out).
"""
import json
import re

import requests

from . import config

CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
STT_URL = "https://api.groq.com/openai/v1/audio/transcriptions"

SARVAM = "https://api.sarvam.ai"
def _lang():
    from . import lang
    return lang

last_error = None
last_provider = None
last_model = None


def groq_available():
    return bool(config.GROQ_API_KEY)


def sarvam_available():
    return bool(config.SARVAM_API_KEY)


def custom_available():
    return bool(config.BRAIN_URL and config.BRAIN_MODEL)


def custom_name():
    return config.BRAIN_NAME or "Your own AI"


def available():
    """Is any language model available to write?"""
    return custom_available() or groq_available() or sarvam_available()


def writers():
    """Who writes, in order: [(name, model)]."""
    out = [(custom_name(), config.BRAIN_MODEL)] if custom_available() else []
    pair = [("Sarvam", config.SARVAM_CHAT_MODEL, sarvam_available()), ("Groq", config.GROQ_MODEL, groq_available())]
    if config.WRITER == "groq":
        pair.reverse()
    return out + [(n, m) for n, m, ok in pair if ok]


def _extract_json(text):
    if not text:
        return None
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return None
    return None


def chat_json(system, user, max_tokens=1800):
    """Ask for a JSON object from the writers in order (your own AI -> Sarvam -> Groq). Returns a dict, or None."""
    global last_provider, last_model
    calls = {"Sarvam": lambda: _sarvam_json(system, user, max_tokens, timeout=config.SARVAM_WRITE_TIMEOUT),
             "Groq": lambda: _groq_json(system, user, max_tokens)}
    for i, (name, model) in enumerate(writers()):
        fn = calls.get(name) or (lambda: _custom_json(system, user, max_tokens))
        data = fn()
        if data is not None:
            last_provider = name if i == 0 else f"{name} (backup)"
            last_model = model
            return data
    return None


def _custom_json(system, user, max_tokens=1800):
    """Bring your own brain: any OpenAI-style chat endpoint (OpenAI, Gemini, Claude, Ollama, vLLM…)."""
    global last_error
    url = config.BRAIN_URL.rstrip("/")
    if not url.endswith("/chat/completions"):
        url += "/chat/completions"
    headers = {"Content-Type": "application/json"}
    if config.BRAIN_KEY:
        headers["Authorization"] = f"Bearer {config.BRAIN_KEY}"
    base = {"model": config.BRAIN_MODEL, "temperature": 0.2, "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    for payload in ({**base, "response_format": {"type": "json_object"}}, base):
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=60)
            if r.status_code in (400, 422):
                last_error = f"{custom_name()} {r.status_code}: {r.text[:200]}"
                continue
            r.raise_for_status()
            data = _extract_json(r.json()["choices"][0]["message"].get("content") or "")
            if data is not None:
                return data
            last_error = f"{custom_name()} returned text that was not JSON"
        except Exception as e:
            last_error = f"{custom_name()} error: {e}"
            break
    return None


def chat_json_via(first, system, user, max_tokens=1800):
    """Like chat_json, but start with a chosen brain ("groq" or "sarvam") so two can work side by side.
    Returns (data, provider)."""
    order = [("groq", groq_available, _groq_json), ("sarvam", sarvam_available, _sarvam_json)]
    if first == "sarvam":
        order.reverse()
    for name, ok, fn in order:
        if ok():
            data = fn(system, user, max_tokens)
            if data is not None:
                return data, ("Groq" if name == "groq" else "Sarvam")
    return None, None


def _sarvam_json(system, user, max_tokens, timeout=90):
    global last_error
    headers = {"api-subscription-key": config.SARVAM_API_KEY, "Content-Type": "application/json"}
    base = {"model": config.SARVAM_CHAT_MODEL, "temperature": 0.2, "max_tokens": max(max_tokens, 2500),
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    for payload in ({**base, "response_format": {"type": "json_object"}, "reasoning_effort": "low"}, base):
        try:
            r = requests.post(f"{SARVAM}/v1/chat/completions", headers=headers, json=payload, timeout=timeout)
            if r.status_code in (400, 422):
                last_error = f"Sarvam {r.status_code}: {r.text[:200]}"
                continue
            r.raise_for_status()
            data = _extract_json(r.json()["choices"][0]["message"].get("content") or "")
            if data is not None:
                return data
            last_error = "Sarvam returned text that was not JSON"
        except Exception as e:
            last_error = f"Sarvam error: {e}"
            break
    return None


def _groq_json(system, user, max_tokens=1800):
    global last_error
    headers = {"Authorization": f"Bearer {config.GROQ_API_KEY}", "Content-Type": "application/json"}
    base = {"model": config.GROQ_MODEL, "temperature": 0.2, "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    attempts = [
        {**base, "response_format": {"type": "json_object"}, "reasoning_effort": "low"},
        {**base, "response_format": {"type": "json_object"}},
        base,  # plainest request, for models that reject the extra options
    ]
    for payload in attempts:
        try:
            r = requests.post(CHAT_URL, headers=headers, json=payload, timeout=60)
            if r.status_code == 429:  # free-tier rate limit: wait once (as long as Groq asks, max 20 s), then retry
                import time
                try:
                    wait = float(r.headers.get("retry-after") or 8)
                except ValueError:
                    wait = 8
                time.sleep(min(max(wait, 1), 20))
                r = requests.post(CHAT_URL, headers=headers, json=payload, timeout=60)
            if r.status_code == 400:
                last_error = f"Groq 400: {r.text[:200]}"
                continue
            r.raise_for_status()
            content = r.json()["choices"][0]["message"].get("content") or ""
            data = _extract_json(content)
            if data is not None:
                last_error = None
                return data
            last_error = "Groq returned text that was not JSON"
        except Exception as e:
            last_error = f"Groq error: {e}"
            break
    return None


def transcribe(audio_bytes, filename="voice.webm", language=None, mime="", industry=None):
    """Kept for old callers: the real pipeline (Sarvam -> Google -> Groq) is in voice.py."""
    from . import voice
    r = voice.transcribe(audio_bytes, filename, mime, language, industry)
    return (r["text"], r["engine"]) if r["text"] else (None, None)


def whisper(audio_bytes, filename="voice.webm", language=None):
    """Groq Whisper: the last-resort ear (weak on Indian languages, so it is only used when Sarvam and Google fail)."""
    global last_error
    if not groq_available():
        return None
    data = {"model": config.GROQ_WHISPER_MODEL, "response_format": "json", "temperature": "0"}
    if language in ("hi", "kn", "en", "ta", "te", "mr", "bn", "gu", "ml", "pa"):
        data["language"] = language
    elif language == "hinglish":
        data["language"] = "hi"
    try:
        r = requests.post(STT_URL, headers={"Authorization": f"Bearer {config.GROQ_API_KEY}"},
                          files={"file": (filename, audio_bytes)}, data=data, timeout=20)
        r.raise_for_status()
        return r.json().get("text", "").strip()
    except Exception as e:
        last_error = f"Groq speech-to-text error: {e}"
        return None


_whisper = whisper


def vision_json(prompt, image_b64, mime="image/jpeg", max_tokens=900):
    """Photo + instruction -> JSON dict (Groq vision model), or None."""
    global last_error
    if not groq_available():
        return None
    headers = {"Authorization": f"Bearer {config.GROQ_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": config.GROQ_VISION_MODEL, "temperature": 0.1, "max_tokens": max_tokens,
               "messages": [{"role": "user", "content": [
                   {"type": "text", "text": prompt},
                   {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{image_b64}"}}]}]}
    for extra in ({"response_format": {"type": "json_object"}}, {}):
        try:
            r = requests.post(CHAT_URL, headers=headers, json={**payload, **extra}, timeout=60)
            if r.status_code == 400 and extra:
                continue
            r.raise_for_status()
            data = _extract_json(r.json()["choices"][0]["message"].get("content") or "")
            if isinstance(data, dict):
                last_error = None
                return data
        except Exception as e:
            last_error = f"Groq vision error: {e}"
            break
    return None


def read_photo(image_b64, mime="image/jpeg", hint=""):
    """Photo -> what the model sees (alarm screen text, codes, visible damage). Returns dict or None."""
    prompt = ("You help a worker describe a problem from a photo (machine alarm screen, nameplate, dish, device display, "
              "error screen, car part). Read any visible text and codes exactly. Return ONLY JSON: "
              '{"what_i_see": "1-2 sentences", "codes": ["exact codes or alarm numbers"], "readings": ["numbers with units"], '
              '"suggested_question": "the question the worker should ask Ustaad, one sentence"}. ' + (f"Context: {hint}" if hint else ""))
    return vision_json(prompt, image_b64, mime, 700)


def speak(text, language="en"):
    """Text -> speech with Sarvam Bulbul. Returns base64 WAV, or None."""
    global last_error
    if not sarvam_available() or not (text or "").strip():
        return None
    try:
        r = requests.post(f"{SARVAM}/text-to-speech",
                          headers={"api-subscription-key": config.SARVAM_API_KEY, "Content-Type": "application/json"},
                          json={"text": text[:2400], "language_code": _lang().SARVAM_CODE.get(language, "en-IN"),
                                "model": config.SARVAM_TTS_MODEL, "pace": 1.0},
                          timeout=60)
        r.raise_for_status()
        audios = r.json().get("audios") or []
        return audios[0] if audios else None
    except Exception as e:
        last_error = f"Sarvam text-to-speech error: {e}"
        return None


def sarvam_translate(texts, language):
    """Kept for old callers: translation now lives in lang.py (codes and numbers are protected there)."""
    from . import lang
    return lang.translate_texts(texts, language)
