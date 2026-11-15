"""
OCR with Sarvam Vision (Sarvam's Document Intelligence): built for Indian documents — 22 Indian languages + English,
tables, scans and handwriting. Used for scanned manual pages, nameplate photos and alarm-screen photos.
Groq's vision AI is only the backup.

Flow (Sarvam's API): send the file -> a job runs -> poll its status -> fetch each page as Markdown.
Every job is logged like the voice pipeline:  [OCR] 7C1D | Sarvam Vision read 12 page(s) in 9.4s
"""
import io
import re
import time
import uuid

import requests

from . import config

JOB = "https://api.sarvam.ai/doc-ai/v1/job"
MAX_PAGES = 20          # picture pages sent per document (Sarvam allows 30 per job)
DONE = {"completed", "partially_completed", "failed", "rejected"}
last_error = None


def available():
    return bool(config.SARVAM_API_KEY)


def _log(trace, msg):
    print(f"[OCR] {trace} | {msg}", flush=True)


def _headers():
    return {"api-subscription-key": config.SARVAM_API_KEY}


def parse(data, filename="document.pdf", mime="application/pdf", language=None, max_wait=80):
    """A PDF or image -> {page_number: markdown}. None if Sarvam is unavailable or the job failed."""
    global last_error
    if not available() or not data:
        return None
    trace, t0 = uuid.uuid4().hex[:4].upper(), time.perf_counter()
    try:
        form = {"language": language} if language else {}
        r = requests.post(f"{JOB}/parse", headers=_headers(), files={"file": (filename, data, mime)}, data=form, timeout=40)
        if r.status_code not in (200, 201):
            raise RuntimeError(f"HTTP {r.status_code}: {r.text[:160]}")
        job = r.json()["job_id"]
        status, wait = r.json().get("status", ""), 1.0
        while status not in DONE:
            if time.perf_counter() - t0 > max_wait:
                raise TimeoutError(f"still '{status}' after {max_wait}s")
            time.sleep(wait)
            wait = min(wait * 1.5, 4)
            s = requests.get(f"{JOB}/{job}/status", headers=_headers(), timeout=20)
            s.raise_for_status()
            status = s.json().get("status", "")
        if status in ("failed", "rejected"):
            raise RuntimeError(f"job {status}")
        res = requests.get(f"{JOB}/{job}/results", headers=_headers(), params={"format": "md"}, timeout=40)
        res.raise_for_status()
        pages = {}
        for doc in res.json().get("documents") or []:
            for p in doc.get("pages") or []:
                text = _clean(p.get("content") or "")
                if text:
                    pages[int(p.get("page_number") or len(pages) + 1)] = text
        _log(trace, f"✅ Sarvam Vision read {len(pages)} page(s) of {filename} in {time.perf_counter() - t0:.1f}s ({status})")
        return pages
    except Exception as e:
        last_error = f"Sarvam Vision error: {e}"
        _log(trace, f"❌ Sarvam Vision failed after {time.perf_counter() - t0:.1f}s ({str(e)[:140]})")
        return None


def _clean(md):
    md = re.sub(r"<[^>]+>", " ", md)                 # stray HTML tags
    md = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", md)     # image links
    return re.sub(r"[ \t]+", " ", md).strip()


def pdf_pages(data, pages, language=None):
    """Send only some pages of a PDF (the picture pages). Returns {original_page_number: markdown}."""
    from pypdf import PdfReader, PdfWriter
    src = PdfReader(io.BytesIO(data))
    pages = [n for n in pages if 1 <= n <= len(src.pages)][:MAX_PAGES]
    if not pages:
        return None
    w = PdfWriter()
    for n in pages:
        w.add_page(src.pages[n - 1])
    buf = io.BytesIO()
    w.write(buf)
    got = parse(buf.getvalue(), "pages.pdf", "application/pdf", language, max_wait=60 + 3 * len(pages))
    if not got:
        return None
    return {pages[i - 1]: text for i, text in got.items() if 1 <= i <= len(pages)}


def image_text(image_bytes, mime="image/jpeg", language=None):
    """A photo (nameplate, alarm screen, logbook page) -> its text as Markdown, or None."""
    ext = {"image/png": ".png", "image/webp": ".webp"}.get((mime or "").split(";")[0], ".jpg")
    got = parse(image_bytes, "photo" + ext, (mime or "image/jpeg").split(";")[0], language, max_wait=45)
    if not got:
        return None
    return "\n\n".join(got[k] for k in sorted(got)).strip() or None


def md_tables(md):
    """Markdown tables -> lists of rows of cells (separator rows dropped)."""
    tables, cur = [], []
    for line in (md or "").split("\n"):
        line = line.strip()
        if line.startswith("|") and line.count("|") >= 2:
            cells = [c.strip() for c in line.strip("|").split("|")]
            if all(re.fullmatch(r":?-{2,}:?", c) or not c for c in cells):
                continue
            cur.append(cells)
        elif cur:
            tables.append(cur)
            cur = []
    if cur:
        tables.append(cur)
    return [t for t in tables if len(t) >= 1]
