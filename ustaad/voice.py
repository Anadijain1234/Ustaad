"""
Voice -> text, built the way the SIH project does it (that one works well on Render):

  1. the browser recording (WebM/Opus, or MP4 on iPhone) is turned into a clean 16 kHz mono WAV with ffmpeg;
  2. SARVAM Saaras v4 hears it first, auto-detecting the language, so Hindi + English + Kannada in one sentence works.
     It also gets this industry's own words (machine IDs, alarm codes, people, parts) as hints, so it hears "CNC-3";
  3. if Sarvam fails or is slow (12 s), GOOGLE speech (free, no key — same library as SIH);
  4. GROQ Whisper only as the very last resort.
Every try is logged with its time, like SIH:   [VOICE-IN] 3F2A | heard by SARVAM in 1.3s | ...
"""
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import uuid

import requests

from . import config, lang, llm, packs, store

SARVAM_STT = "https://api.sarvam.ai/speech-to-text"
SARVAM_TIMEOUT = 12
MAX_SECONDS = 29.5          # Sarvam's quick API is for clips under 30 s
EXT = {"webm": ".webm", "ogg": ".ogg", "mp4": ".m4a", "m4a": ".m4a", "mpeg": ".mp3", "mp3": ".mp3", "wav": ".wav",
       "x-wav": ".wav", "aac": ".aac", "3gpp": ".3gp", "flac": ".flac"}
_hint_cache = {}


def _log(trace, msg):
    print(f"[VOICE-IN] {trace} | {msg}", flush=True)


def ffmpeg():
    return shutil.which("ffmpeg")


def _ext(name, mime):
    sub = (mime or "").split(";")[0].split("/")[-1].strip().lower()
    if sub in EXT:
        return EXT[sub]
    e = os.path.splitext(name or "")[1].lower()
    return e if 1 < len(e) <= 5 else ".webm"


def to_wav(data, name="voice.webm", mime=""):
    """Any browser recording -> 16 kHz mono 16-bit WAV (cut at 29.5 s). None if ffmpeg is missing or can't read it."""
    exe = ffmpeg()
    if not exe or not data:
        return None
    with tempfile.TemporaryDirectory() as d:
        src, dst = os.path.join(d, "in" + _ext(name, mime)), os.path.join(d, "out.wav")
        with open(src, "wb") as f:
            f.write(data)
        try:
            r = subprocess.run([exe, "-hide_banner", "-loglevel", "error", "-y", "-i", src, "-t", str(MAX_SECONDS),
                                "-ac", "1", "-ar", "16000", "-sample_fmt", "s16", dst], capture_output=True, timeout=25)
        except Exception:
            return None
        if r.returncode != 0 or not os.path.exists(dst) or os.path.getsize(dst) <= 44:
            return None
        with open(dst, "rb") as f:
            return f.read()


def seconds(wav):
    return max(0.0, (len(wav or b"") - 44) / 32000)  # 16 kHz × 2 bytes × 1 channel


def status():
    """Which ears are ready, in order (shown in /api/status so a deploy can be checked)."""
    import importlib.util
    google = importlib.util.find_spec("speech_recognition") is not None
    order = [n for n, ok in (("Sarvam", bool(config.SARVAM_API_KEY)), ("Google", google and bool(ffmpeg())),
                             ("Groq", llm.groq_available())) if ok]
    return {"order": order, "ffmpeg": bool(ffmpeg()), "google_library": google}


# ---------- this industry's own words ----------
def hints(industry):
    """Up to 50 words Sarvam should listen for: machine IDs and models, alarm codes, people's names, part names."""
    if not industry:
        return []
    hit = _hint_cache.get(industry)
    if hit and time.time() - hit[0] < 600:
        return hit[1]
    terms = []
    try:
        assets = packs.assets(industry)
        terms += [a["id"] for a in assets]
        terms += [r["code"] for r in store.records(industry) if r.get("code")]
        terms += [p["name"] for p in packs.get(industry).get("people", [])]
        terms += [a.get("model", "") for a in assets]
        terms += [c["name"] for a in assets for c in a.get("components") or []]
    except Exception:
        pass
    seen, out = set(), []
    for t in terms:
        t = str(t or "").strip()[:64]
        if len(t) >= 2 and t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
    out = out[:50]
    _hint_cache[industry] = (time.time(), out)
    return out


def tidy(text, industry=None):
    """Small fixes after hearing: Indian digits -> 0-9, 'cnc 3' / 'C N C 3' -> 'CNC-3' (the real machine ID)."""
    text = lang.ascii_digits(text or "").strip()
    if not industry:
        return text
    try:
        ids = [a["id"] for a in packs.assets(industry)]
    except Exception:
        return text
    for aid in sorted(ids, key=len, reverse=True):
        parts = [p for p in re.split(r"[-_\s]+", aid) if p]
        if len(parts) < 2:
            continue
        spell = lambda p: r"[\s.]*".join(map(re.escape, p)) if p.isalpha() and len(p) <= 4 else re.escape(p)  # noqa: E731
        pat = r"(?<![\w-])" + r"\s*[-‐–]?\s*".join(spell(p) for p in parts) + r"(?![\w-])"
        text = re.sub(pat, aid, text, flags=re.I)
    return text


# ---------- the three engines ----------
def _sarvam(audio, fname, mime, terms):
    data = {"model": config.SARVAM_STT_MODEL, "language_code": "unknown"}
    if terms and config.SARVAM_STT_MODEL.startswith("saaras:v4"):
        data["keyterms"] = json.dumps(terms, ensure_ascii=False)
    post = lambda d: requests.post(SARVAM_STT, headers={"api-subscription-key": config.SARVAM_API_KEY},  # noqa: E731
                                   files={"file": (fname, audio, mime)}, data=d, timeout=SARVAM_TIMEOUT)
    r = post(data)
    if r.status_code in (400, 422) and "keyterms" in data:  # hints refused -> once more without them
        data.pop("keyterms")
        r = post(data)
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:160]}")
    j = r.json()
    return (j.get("transcript") or "").strip(), j.get("language_code")


def _google(wav, language):
    import speech_recognition as sr  # the same free Google speech library SIH uses
    rec = sr.Recognizer()
    rec.operation_timeout = 10
    with sr.AudioFile(io.BytesIO(wav)) as source:
        audio = rec.record(source)
    try:
        return rec.recognize_google(audio, language=lang.GOOGLE_CODE.get(language, "en-IN")).strip()
    except sr.UnknownValueError:
        return ""


def transcribe(audio_bytes, filename="voice.webm", mime="", language=None, industry=None):
    """Returns {"text", "engine", "language", "seconds", "tries"}; text is "" if nobody could hear words."""
    trace = uuid.uuid4().hex[:4].upper()
    t0 = time.perf_counter()
    tries = []
    wav = to_wav(audio_bytes, filename, mime)
    if wav:
        _log(trace, f"recording {len(audio_bytes) // 1024} KB -> clean WAV {seconds(wav):.1f}s | order: SARVAM -> GOOGLE -> GROQ")
        audio, fname, amime = wav, "audio.wav", "audio/wav"
    else:
        _log(trace, f"recording {len(audio_bytes) // 1024} KB sent as it is ({'no ffmpeg' if not ffmpeg() else 'ffmpeg could not read it'})")
        audio, fname, amime = audio_bytes, "audio" + _ext(filename, mime), (mime or "audio/webm").split(";")[0]

    def done(text, engine, detected=None):
        text = tidy(text, industry)
        took = round(time.perf_counter() - t0, 1)
        _log(trace, f"✅ heard by {engine.upper()} | total {took}s | language: {detected or language or '?'} | '{text[:120]}'")
        return {"text": text, "engine": engine, "language": lang.FROM_SARVAM.get(detected or "", None), "seconds": took,
                "tries": tries}

    if config.SARVAM_API_KEY:
        t = time.perf_counter()
        try:
            text, detected = _sarvam(audio, fname, amime, hints(industry))
            tries.append({"engine": "Sarvam", "ok": bool(text), "seconds": round(time.perf_counter() - t, 1)})
            if text:
                return done(text, "Sarvam", detected)
            _log(trace, "SARVAM heard no words -> trying GOOGLE")
        except Exception as e:
            tries.append({"engine": "Sarvam", "ok": False, "seconds": round(time.perf_counter() - t, 1), "error": str(e)[:120]})
            _log(trace, f"❌ SARVAM failed in {time.perf_counter() - t:.1f}s ({str(e)[:120]}) -> trying GOOGLE")
    if wav:
        t = time.perf_counter()
        try:
            text = _google(wav, language or "en")
            tries.append({"engine": "Google", "ok": bool(text), "seconds": round(time.perf_counter() - t, 1)})
            if text:
                return done(text, "Google")
            _log(trace, "GOOGLE heard no words -> trying GROQ")
        except Exception as e:
            tries.append({"engine": "Google", "ok": False, "seconds": round(time.perf_counter() - t, 1), "error": str(e)[:120]})
            _log(trace, f"❌ GOOGLE failed in {time.perf_counter() - t:.1f}s ({type(e).__name__}: {str(e)[:80]}) -> trying GROQ")
    if llm.groq_available():
        t = time.perf_counter()
        text = llm.whisper(audio, fname, language)
        tries.append({"engine": "Groq", "ok": bool(text), "seconds": round(time.perf_counter() - t, 1)})
        if text:
            return done(text, "Groq (backup)")
        _log(trace, f"❌ GROQ failed ({llm.last_error})")
    _log(trace, f"💥 nobody could hear words (total {time.perf_counter() - t0:.1f}s)")
    return {"text": "", "engine": None, "language": None, "seconds": round(time.perf_counter() - t0, 1), "tries": tries}
