"""
Languages. Rule: Groq thinks and writes in English (what it is best at); Sarvam does every Indian language
(what it is best at). So:
  - a question typed or spoken in an Indian script is translated to English by Sarvam before searching and answering;
  - answers, SOPs, shift reports and interview questions are written in English, then translated by Sarvam;
  - memory itself stays in English, so a fix said in Kannada is found by a question asked in Hindi.
Codes, machine IDs and numbers must survive translation: if Sarvam drops one, it is added back in brackets.
"""
import re
from concurrent.futures import ThreadPoolExecutor

import requests

from . import config

SARVAM = "https://api.sarvam.ai"
# code: (menu label, name used in AI prompts, Sarvam code, Google speech code)
LANGS = {
    "en": ("English", "English", "en-IN", "en-IN"),
    "hi": ("हिन्दी", "Hindi (Devanagari script, simple words)", "hi-IN", "hi-IN"),
    "hinglish": ("Hinglish", "Hinglish (Hindi in Roman script, simple words)", "hi-IN", "hi-IN"),
    "kn": ("ಕನ್ನಡ", "Kannada (simple words)", "kn-IN", "kn-IN"),
    "ta": ("தமிழ்", "Tamil (simple words)", "ta-IN", "ta-IN"),
    "te": ("తెలుగు", "Telugu (simple words)", "te-IN", "te-IN"),
    "mr": ("मराठी", "Marathi (simple words)", "mr-IN", "mr-IN"),
    "bn": ("বাংলা", "Bengali (simple words)", "bn-IN", "bn-IN"),
    "gu": ("ગુજરાતી", "Gujarati (simple words)", "gu-IN", "gu-IN"),
    "ml": ("മലയാളം", "Malayalam (simple words)", "ml-IN", "ml-IN"),
    "pa": ("ਪੰਜਾਬੀ", "Punjabi (Gurmukhi script, simple words)", "pa-IN", "pa-IN"),
    "od": ("ଓଡ଼ିଆ", "Odia (simple words)", "od-IN", "or-IN"),
}
NAMES = {k: v[1] for k, v in LANGS.items()}
SARVAM_CODE = {k: v[2] for k, v in LANGS.items()}
GOOGLE_CODE = {k: v[3] for k, v in LANGS.items()}
FROM_SARVAM = {v[2]: k for k, v in LANGS.items() if k != "hinglish"}

INDIC = re.compile(r"[ऀ-෿਀-੿]")  # Devanagari … Malayalam/Sinhala blocks
# Indian-script digits -> 0-9 (Sarvam sometimes writes २०४१ for 2041)
DIGITS = {}
for _base in (0x0966, 0x09E6, 0x0A66, 0x0AE6, 0x0B66, 0x0BE6, 0x0C66, 0x0CE6, 0x0D66):
    for _i in range(10):
        DIGITS[_base + _i] = str(_i)
CODE = re.compile(r"\b[A-Za-z]{1,6}-[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*\b|\b[A-Z]{0,4}\d[\d.,:/]*[A-Za-z]{0,3}\b")
CHUNK = 900  # Sarvam's translate takes up to 1000 characters

last_error = None


def ascii_digits(text):
    return (text or "").translate(DIGITS)


def has_indic(text):
    return bool(INDIC.search(text or ""))


def available():
    return bool(config.SARVAM_API_KEY)


def _codes(text):
    """IDs and numbers that must survive translation: 'CNC-3', '2041', '0.02' (single digits like '3 times' are free)."""
    out = set()
    for m in CODE.finditer(text or ""):
        c = m.group(0).rstrip(".,:/")
        digits = sum(ch.isdigit() for ch in c)
        if ("-" in c and digits) or digits >= 2:
            out.add(c)
    return out


def _pieces(text):
    """Split into lines (bullets kept) and then into pieces under the size limit, at sentence ends."""
    out = []
    for line in (text or "").split("\n"):
        m = re.match(r"^(\s*(?:[-•*]|\d+[.)])?\s*)(.*)$", line)
        prefix, body = m.group(1), m.group(2)
        if len(body) <= CHUNK:
            out.append((prefix, [body]))
            continue
        parts, cur = [], ""
        words = []  # sentences, and very long sentences cut at spaces
        for sent in re.split(r"(?<=[.!?।])\s+", body):
            words += [sent] if len(sent) <= CHUNK else re.findall(r".{1,%d}(?:\s+|$)" % CHUNK, sent)
        for w in words:
            if len(cur) + len(w) + 1 > CHUNK and cur:
                parts.append(cur)
                cur = ""
            cur = (cur + " " + w.strip()).strip()[:CHUNK]
        if cur:
            parts.append(cur)
        out.append((prefix, parts))
    return out


def _sarvam_one(text, target, src="auto"):
    extra = {"output_script": "roman"} if target == "hinglish" else {}
    r = requests.post(f"{SARVAM}/translate",
                      headers={"api-subscription-key": config.SARVAM_API_KEY, "Content-Type": "application/json"},
                      json={"input": text, "source_language_code": src, "target_language_code": SARVAM_CODE.get(target, "hi-IN"),
                            "model": config.SARVAM_TRANSLATE_MODEL, "mode": "modern-colloquial", **extra},
                      timeout=20)
    r.raise_for_status()
    return r.json().get("translated_text") or text


def translate_texts(texts, target, src="auto"):
    """Translate a list of strings with Sarvam. Returns the list, or None if Sarvam is unavailable or failed."""
    global last_error
    if not available():
        return None
    jobs = []  # (text_index, line_index, piece_index, piece)
    shape = []
    for ti, t in enumerate(texts):
        lines = _pieces(t if isinstance(t, str) else "")
        shape.append(lines)
        for li, (_, parts) in enumerate(lines):
            for pi, p in enumerate(parts):
                if p.strip() and re.search(r"[^\W\d_]", p):  # has letters (skip numbers-only pieces)
                    jobs.append((ti, li, pi, p))
    done = {}
    try:
        with ThreadPoolExecutor(max_workers=8) as ex:
            for (ti, li, pi, _), out in zip(jobs, ex.map(lambda j: _sarvam_one(j[3], target, src), jobs)):
                done[(ti, li, pi)] = out
    except Exception as e:
        last_error = f"Sarvam translate error: {e}"
        return None
    result = []
    for ti, lines in enumerate(shape):
        if not isinstance(texts[ti], str):
            result.append(texts[ti])
            continue
        out_lines = []
        for li, (prefix, parts) in enumerate(lines):
            out_lines.append(prefix + " ".join(done.get((ti, li, pi), p) for pi, p in enumerate(parts)))
        out = "\n".join(out_lines)
        missing = [c for c in _codes(texts[ti]) if c not in ascii_digits(out)]
        if missing:  # a code or number got lost or spelled out: put it back so nothing important is missing
            out = f"{out} ({', '.join(sorted(missing))})"
        result.append(out)
    return result


def to_english(text):
    """A question or log in an Indian script -> English for searching memory and for Groq. Returns (english, changed)."""
    text = (text or "").strip()
    if not has_indic(text) or not available():
        return text, False
    out = translate_texts([text], "en", "auto")
    if out and out[0] and out[0].strip() != text:
        return out[0].strip(), True
    return text, False


# which fields of each kind of result are words for people (IDs, refs and numbers are left alone)
ANSWER_FIELDS = {"summary": True, "check_first": True, "steps": True, "expert_tip": True, "manual_vs_team": True,
                 "estimated_time": True, "safety": True, "likely_causes": ["cause", "why"], "avoid": ["action", "why"]}
SOP_FIELDS = {"title": True, "when_to_use": True, "symptoms": True, "first_checks": True, "steps": True, "tools": True,
              "do_not": True, "safety": True, "typical_time": True}


def translate_obj(obj, target, fields, translator=None):
    """Translate the listed fields of a dict (strings, lists of strings, lists of dicts) in one batch.
    Returns a new dict, or None if the translator (Sarvam by default) couldn't do it."""
    if target == "en":
        return obj
    slots, texts = [], []

    def add(get, put):
        v = get()
        if isinstance(v, str) and v.strip():
            slots.append(put)
            texts.append(v)
    out = {k: (list(v) if isinstance(v, list) else v) for k, v in obj.items()}
    for key, sub in fields.items():
        v = out.get(key)
        if isinstance(v, str):
            add(lambda k=key: out[k], lambda t, k=key: out.__setitem__(k, t))
        elif isinstance(v, list):
            for i, item in enumerate(v):
                if isinstance(item, str):
                    add(lambda k=key, i=i: out[k][i], lambda t, k=key, i=i: out[k].__setitem__(i, t))
                elif isinstance(item, dict) and isinstance(sub, list):
                    out[key][i] = item = dict(item)
                    for s in sub:
                        add(lambda d=item, s=s: d.get(s), lambda t, d=item, s=s: d.__setitem__(s, t))
    if not texts:
        return out
    done = (translator or translate_texts)(texts, target)
    if not done or len(done) != len(texts):
        return None
    for put, t in zip(slots, done):
        put(t)
    return out
