"""Voice + languages, offline (Sarvam, Google and Groq are fakes).  Run:  python tests/test_voice.py
Checks: recording -> clean WAV (ffmpeg), the order Sarvam -> Google -> Groq, machine words as hints, 'cnc 3' -> 'CNC-3',
Hindi digits -> 0-9, answers written in English then translated (memory stays English), codes kept through translation."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import types
from pathlib import Path

for _k in ("HINDSIGHT_API_KEY", "GROQ_API_KEY", "SARVAM_API_KEY", "GITHUB_TOKEN", "GITHUB_REPO"):
    os.environ[_k] = ""
os.environ["DB_PATH"] = str(Path(tempfile.mkdtemp()) / "test.db")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import app as A  # noqa: E402,F401
from ustaad import agent, config, lang, llm, machines, ocr, store, voice  # noqa: E402


class Resp:
    def __init__(self, code, body):
        self.status_code, self._b, self.text = code, body, json.dumps(body)

    def json(self):
        return self._b

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class Fake:
    """Swap things in for one test and put them back."""
    def __init__(self, **swaps):
        self.swaps, self.old = swaps, {}

    def __enter__(self):
        for key, val in self.swaps.items():
            obj, attr = key.rsplit("__", 1)
            target = {"config": config, "voice": voice, "llm": llm, "lang": lang, "requests_voice": voice.requests,
                      "requests_lang": lang.requests, "requests_ocr": ocr.requests, "ocr": ocr}[obj]
            self.old[(target, attr)] = getattr(target, attr)
            setattr(target, attr, val)
        return self

    def __exit__(self, *a):
        for (target, attr), val in self.old.items():
            setattr(target, attr, val)


def _webm(seconds=2):
    d = tempfile.mkdtemp()
    out = os.path.join(d, "x.webm")
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
                    "-c:a", "libopus", out], check=True)
    return Path(out).read_bytes()


def test_recording_becomes_clean_wav_and_is_cut_at_29_5_s():
    if not shutil.which("ffmpeg"):
        print("  (skipped: no ffmpeg)")
        return
    wav = voice.to_wav(_webm(2), "voice.webm", "audio/webm;codecs=opus")
    assert wav[:4] == b"RIFF" and 1.8 < voice.seconds(wav) < 2.3
    assert int.from_bytes(wav[24:28], "little") == 16000 and int.from_bytes(wav[22:24], "little") == 1  # 16 kHz mono
    long = voice.to_wav(_webm(35), "voice.webm", "audio/webm")
    assert voice.seconds(long) <= 29.6
    assert voice.to_wav(b"not audio at all", "x.webm", "audio/webm") is None


def test_machine_words_and_tidy():
    terms = voice.hints("factory")
    assert "CNC-3" in terms and len(terms) <= 50 and all(len(t) <= 64 for t in terms)
    assert voice.tidy("cnc 3 par alarm २०४१ aa raha hai", "factory") == "CNC-3 par alarm 2041 aa raha hai"
    assert voice.tidy("C N C - 3 is whistling", "factory") == "CNC-3 is whistling"
    assert voice.tidy("the cnc machine", "factory") == "the cnc machine"  # no number -> not a machine ID


def test_sarvam_first_with_hints():
    sent = []

    def post(url, headers=None, files=None, data=None, timeout=None):
        sent.append({"url": url, "data": dict(data), "file": files["file"], "timeout": timeout})
        return Resp(200, {"transcript": "cnc 3 se seeti ki awaaz", "language_code": "hi-IN"})
    with Fake(config__SARVAM_API_KEY="k", requests_voice__post=post):
        r = voice.transcribe(_webm(1) if shutil.which("ffmpeg") else b"x" * 100, "voice.webm", "audio/webm", "en", "factory")
    assert r["engine"] == "Sarvam" and r["text"] == "CNC-3 se seeti ki awaaz" and r["language"] == "hi"
    d = sent[0]["data"]
    assert d["language_code"] == "unknown" and d["model"] == config.SARVAM_STT_MODEL and sent[0]["timeout"] == 12
    assert "CNC-3" in json.loads(d["keyterms"])
    if shutil.which("ffmpeg"):
        assert sent[0]["file"][0] == "audio.wav" and sent[0]["file"][2] == "audio/wav"


def test_hints_refused_then_retry_without():
    calls = []

    def post(url, headers=None, files=None, data=None, timeout=None):
        calls.append(dict(data))
        return Resp(422, {"error": {"message": "bad keyterms"}}) if "keyterms" in data else Resp(200, {"transcript": "hello", "language_code": "en-IN"})
    with Fake(config__SARVAM_API_KEY="k", requests_voice__post=post):
        r = voice.transcribe(b"x" * 2000, "voice.webm", "audio/webm", "en", "factory")
    assert r["engine"] == "Sarvam" and len(calls) == 2 and "keyterms" not in calls[1]


def test_fallback_google_then_groq():
    if not shutil.which("ffmpeg"):
        print("  (skipped: no ffmpeg)")
        return
    sr = types.ModuleType("speech_recognition")

    class UnknownValueError(Exception):
        pass

    class AudioFile:
        def __init__(self, f):
            self.f = f

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class Recognizer:
        mode = "ok"

        def record(self, src):
            return src.f.read()

        def recognize_google(self, audio, language="en-IN"):
            assert audio[:4] == b"RIFF" and language == "kn-IN"
            if Recognizer.mode == "ok":
                return "google heard this"
            raise UnknownValueError()
    sr.Recognizer, sr.AudioFile, sr.UnknownValueError = Recognizer, AudioFile, UnknownValueError
    sys.modules["speech_recognition"] = sr

    def down(*a, **k):
        raise TimeoutError("Sarvam too slow")
    audio = _webm(1)
    try:
        with Fake(config__SARVAM_API_KEY="k", requests_voice__post=down):
            r = voice.transcribe(audio, "voice.webm", "audio/webm", "kn", "factory")
        assert r["engine"] == "Google" and r["text"] == "google heard this"
        assert r["tries"][0]["engine"] == "Sarvam" and not r["tries"][0]["ok"]
        Recognizer.mode = "nothing"
        with Fake(config__SARVAM_API_KEY="k", requests_voice__post=down, llm__groq_available=lambda: True,
                  llm__whisper=lambda a, f, l: "groq heard this"):
            r = voice.transcribe(audio, "voice.webm", "audio/webm", "kn", "factory")
        assert r["engine"] == "Groq (backup)" and [t["engine"] for t in r["tries"]] == ["Sarvam", "Google", "Groq"]
        with Fake(config__SARVAM_API_KEY="k", requests_voice__post=down, llm__groq_available=lambda: False):
            r = voice.transcribe(audio, "voice.webm", "audio/webm", "kn", "factory")
        assert r["text"] == "" and r["engine"] is None
    finally:
        sys.modules.pop("speech_recognition", None)


def _fake_translate(calls):
    def post(url, headers=None, json=None, timeout=None):
        calls.append(json)
        t = json["input"]
        if json["target_language_code"] == "en-IN":
            return Resp(200, {"translated_text": "alarm 2041 whistling at high rpm"})
        return Resp(200, {"translated_text": "[" + json["target_language_code"] + "] " + t.replace("CNC-3", "सीएनसी-3")})
    return post


def test_translation_keeps_codes_bullets_and_long_text():
    calls = []
    with Fake(config__SARVAM_API_KEY="k", requests_lang__post=_fake_translate(calls)):
        out = lang.translate_texts(["Check CNC-3 coupling, under 0.02 mm.", "- first line\n- second line", "word " * 400], "hi")
    assert out[0].startswith("[hi-IN]") and "(CNC-3)" in out[0] and "0.02" in out[0]  # lost code put back
    assert out[1].split("\n")[0].startswith("- [hi-IN]") and out[1].split("\n")[1].startswith("- [hi-IN]")
    assert all(len(c["input"]) <= 1000 for c in calls) and len(calls) >= 5  # 2000-char text was split
    assert all(c["source_language_code"] == "auto" for c in calls)


def test_hindi_question_english_memory_translated_answer():
    calls = []
    with Fake(config__SARVAM_API_KEY="k", requests_lang__post=_fake_translate(calls), llm__available=lambda: False):
        res = agent.ask("factory", "CNC-3", "सीएनसी-3 पर अलार्म 2041, तेज़ आरपीएम पर सीटी की आवाज़", True, "hi")
    assert res["question_translated"] and res["problem_en"] == "alarm 2041 whistling at high rpm"
    assert res["translated_by"] == "Sarvam" and res["answer"]["summary"].startswith("[hi-IN]")
    assert not res["answer_en"]["summary"].startswith("[")
    saved = store.ask(res["ask_id"])
    assert not saved["answer"]["summary"].startswith("[") and saved["problem"] == "alarm 2041 whistling at high rpm"  # memory: English
    assert any("2041" in (c.get("text") or "") for c in res["memories"])  # the English question found the right memory


def test_tip_in_kannada_saved_in_english_with_original():
    calls = []
    with Fake(config__SARVAM_API_KEY="k", requests_lang__post=_fake_translate(calls)):
        r = agent.add_tip("factory", "ramesh", "CNC-3", "ಕಪ್ಲಿಂಗ್ ಅಲೈನ್ಮೆಂಟ್ ಮೊದಲು ಪರಿಶೀಲಿಸಿ", "test")
    assert r["tip"]["text"].startswith("alarm 2041") and "[original: ಕಪ್ಲಿಂಗ್" in r["tip"]["text"]


def test_scanned_pdf_read_by_sarvam_vision():
    import io
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (600, 400), "white").save(buf, format="PDF")
    sent = {}

    def post(url, headers=None, files=None, data=None, timeout=None):
        sent["file"] = files["file"][0]
        return Resp(201, {"job_id": "J1", "status": "queued", "run_id": "R"})

    def get(url, headers=None, params=None, timeout=None):
        if url.endswith("/status"):
            return Resp(200, {"job_id": "J1", "status": "completed"})
        md = "VMC-850 Machining centre\n\n| Item | Value |\n|---|---|\n| Spindle speed | 8000 rpm |\n| Supply voltage | 415 V |"
        return Resp(200, {"documents": [{"file_name": "pages.pdf", "pages": [{"page_number": 1, "content": md}]}]})
    with Fake(config__SARVAM_API_KEY="k", requests_ocr__post=post, requests_ocr__get=get, llm__available=lambda: False):
        d = machines.read_source("factory", file=(buf.getvalue(), "scan.pdf", "application/pdf"))
    f = {x["key"]: x for x in d["spec_fields"]}
    assert sent["file"] == "pages.pdf" and d["read"]["sources"][0].get("ocr_pages") == [1]
    assert f["spindle_speed"]["value"].startswith("8000") and f["voltage"]["status"] in ("verified", "converted")


def test_status_reports_voice_order():
    st = A.app.test_client().get("/api/status").get_json()
    assert "voice" in st and isinstance(st["voice"]["order"], list)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok ", name)
    print("Voice tests passed.")
