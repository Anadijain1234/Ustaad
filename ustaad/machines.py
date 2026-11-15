"""
My machines — the team's register of its machines / equipment / devices / vehicles.

  add      -> fill a machine's details from the maker's PDF manual, its product web page or a photo of its nameplate
              (the AI reads it, a senior checks the form, then saves). The manual's known faults and service tasks are
              saved into Hindsight as "Maker's manual" memories, so answers can say "manual says X, the team found Y".
  profile  -> one page per machine: specs, health light, service due, spare-parts stock, warranty, full fix history,
              who knows it best, its manual memories and a QR sticker.
  sensors  -> a sensor alert opens a half-filled log by itself; normal readings after a fix mark it "sensor-confirmed".
"""
import html as htmllib
import ipaddress
import io
import json
import re
import socket
from datetime import date, datetime, timedelta
from urllib.parse import urljoin, urlparse

import requests

from . import config, llm, packs, reader, specs, store
from .memory import manual_to_memory, memory, record_to_memory

PAGE_WORDS = re.compile(r"alarm|trouble|fault|error|maint|lubric|specif|clean|filter|replac|inspect|warrant|daily|weekly|"
                        r"monthly|pressure|temperature|pilot|thermostat|service|parts? list|capacity|voltage|power", re.I)
MAX_TEXT = 13000


# ---------- reading a source: web page, PDF, photo ----------
def _check_url(url):
    u = urlparse((url or "").strip())
    if u.scheme not in ("http", "https") or not u.hostname:
        raise ValueError("Please paste a full web link that starts with https://")
    try:
        infos = socket.getaddrinfo(u.hostname, None)
    except Exception:
        raise ValueError("Couldn't find that website. Check the link.")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise ValueError("That link points to a private network address, so Ustaad won't open it.")
    return u.geturl()


def fetch_page(url):
    """Open a maker's product page (or a PDF link) safely and return its readable text."""
    url = _check_url(url)
    headers = {"User-Agent": "Mozilla/5.0 (compatible; UstaadBot/1.0; reads product pages a user pasted)",
               "Accept-Language": "en-IN,en;q=0.8"}
    try:
        for _ in range(4):  # follow redirects ourselves, checking every hop
            r = requests.get(url, headers=headers, timeout=20, stream=True, allow_redirects=False)
            if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("location"):
                url = _check_url(urljoin(url, r.headers["location"]))
                continue
            break
        r.raise_for_status()
        raw = r.raw.read(4_000_000, decode_content=True)
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"Couldn't open that page ({str(e)[:100]}). Some company sites block servers — "
                         "upload the PDF manual instead.")
    if "pdf" in r.headers.get("content-type", "") or raw[:4] == b"%PDF":
        return pdf_text(raw)
    text = html_to_text(raw.decode(r.encoding or "utf-8", errors="ignore"))
    if len(text) < 200:
        raise ValueError("That page has almost no readable text (it may need JavaScript). Upload the PDF manual instead.")
    return text


def html_to_text(html):
    html = re.sub(r"(?is)<(script|style|noscript|svg|nav|footer|header|form|iframe)[^>]*>.*?</\1>", " ", html)
    html = re.sub(r"(?i)<(br|/p|/li|/tr|/h[1-6]|/div|/td|/th|/dt|/dd)[^>]*>", "\n", html)
    html = re.sub(r"(?i)<(td|th|dd)[^>]*>", " | ", html)
    text = htmllib.unescape(re.sub(r"<[^>]+>", " ", html))
    lines, seen = [], set()
    for line in (re.sub(r"[ \t\r\f\v|]+", " ", x).strip(" |") for x in text.split("\n")):
        if len(line) > 2 and line.lower() not in seen:
            seen.add(line.lower())
            lines.append(line)
    return "\n".join(lines)


def pdf_text(data):
    """Text of a PDF manual. Long manuals: keep the first pages plus the pages that talk about specs, maintenance,
    alarms and faults, up to about 12,000 characters."""
    try:
        from pypdf import PdfReader
    except ImportError:
        raise ValueError("PDF reading needs the 'pypdf' package (it is in requirements.txt).")
    try:
        reader = PdfReader(io.BytesIO(data))
        pages = [re.sub(r"[ \t|]+", " ", (p.extract_text() or "")).strip() for p in reader.pages[:400]]
    except Exception as e:
        raise ValueError(f"Couldn't read that PDF: {str(e)[:100]}")
    pages = [re.sub(r"\n\s*\n+", "\n", p) for p in pages]
    if sum(len(p) for p in pages) < 200:
        raise ValueError("This PDF has no selectable text (it is a scanned picture). Try another manual or the maker's web page.")
    if sum(len(p) for p in pages) <= MAX_TEXT:
        return "\n\n".join(p for p in pages if p)
    keep = {0, 1}
    must = re.compile(r"specification|technical data|alarm list|troubleshoot|trouble shoot|parts? list|parts diagram|"
                      r"maintenance schedule|daily maintenance|warranty|power requirement", re.I)

    def score(i):
        return len(PAGE_WORDS.findall(pages[i])) / (1 + len(pages[i]) / 3000) + (30 if must.search(pages[i]) else 0)
    ranked = sorted(range(len(pages)), key=lambda i: -score(i))
    pages = [x[:2200] for x in pages]  # long pages are cut, so more useful pages fit
    size = len(pages[0]) + len(pages[1] if len(pages) > 1 else "")
    for i in ranked:
        if size > MAX_TEXT:
            break
        if pages[i] and (len(PAGE_WORDS.findall(pages[i])) >= 2 or must.search(pages[i])):
            keep.add(i)
            size += len(pages[i])
    return "\n\n".join(f"[page {i + 1}] {pages[i]}" for i in sorted(keep) if i < len(pages) and pages[i])[:MAX_TEXT + 1000]


EXTRACT_SCHEMA = """Return ONLY JSON:
{"name": "short plain name, e.g. 'Vertical machining centre' or 'Gas fryer'",
 "maker": "", "model": "", "type": "one or two words",
 "summary": "one plain sentence: what it is and what it is used for",
 "specs": [{"label": "e.g. Supply voltage", "value": "e.g. 380 V, 3 phase"}],
 "components": [{"name": "a part that wears out or gets replaced", "part_no": "", "every_days": null}],
 "faults": [{"title": "short fault name", "code": "alarm/error code or empty", "symptoms": "", "cause": "", "fix": "what the manual says to do"}],
 "service": [{"task": "maintenance task", "every_days": 1}],
 "warranty_months": null}"""


def extract(industry, text, source_ref=""):
    """Turn a manual / product page into a draft register entry. A senior checks the form before saving."""
    pk = packs.get(industry)
    text = (text or "").strip()
    if len(text) < 80:
        raise ValueError("Not enough text to read. Paste more, or upload the PDF manual.")
    data = None
    if llm.available():
        data = llm.chat_json(
            f"You read a maker's manual or product page for a {pk['labels']['asset'].lower()} and fill a register entry for a "
            f"{pk['name'].lower()} team. Use ONLY facts written in the text — never invent numbers, codes or part numbers; "
            "leave a field empty if the text doesn't say it. Keep alarm/error codes exactly. specs: up to 10 most useful. "
            "components: up to 10 parts that wear out or are replaced, with part numbers if given. faults: up to 8 — include "
            "alarm codes from any alarm/troubleshooting list. service: up to 8 tasks with every_days (daily 1, weekly 7, "
            "monthly 30, quarterly 90, half-yearly 180, yearly 365). Simple English. If the page covers a range of models, "
            "give the range.", f"Text (from {source_ref or 'the user'}):\n{text[:MAX_TEXT]}\n\n{EXTRACT_SCHEMA}", max_tokens=2600)
    if not isinstance(data, dict):
        specs = [{"label": m.group(1).strip()[:40], "value": m.group(2).strip()[:60]}
                 for m in re.finditer(r"^([A-Za-z][A-Za-z ()/.-]{2,40})\s*[:=]\s*([^\n]{1,60})$", text, re.M)][:10]
        first = re.sub(r"^\[page \d+\]\s*", "", next((ln for ln in text.splitlines() if len(ln.strip()) > 3), "New item")).strip()[:60]
        data = {"name": first, "maker": "", "model": "", "type": "", "summary": "", "specs": specs, "components": [],
                "faults": [], "service": [], "warranty_months": None,
                "note": "Filled without AI (no key) — only simple 'label: value' lines were picked up. Please check."}
    return _clean_draft(industry, data, source_ref)


def from_photo(industry, image_b64, mime):
    """Photo of a nameplate / rating plate -> draft register entry."""
    pk = packs.get(industry)
    data = llm.vision_json(
        f"This is a photo of a {pk['labels']['asset'].lower()}'s nameplate / rating plate / label. Read the visible text "
        "exactly. Return ONLY JSON: {\"name\": \"plain name of the item\", \"maker\": \"\", \"model\": \"\", \"serial\": \"\", "
        "\"year\": \"\", \"type\": \"\", \"specs\": [{\"label\": \"\", \"value\": \"\"}]}. Leave unknown fields empty.",
        image_b64, mime)
    if not isinstance(data, dict):
        raise ValueError("Couldn't read the nameplate" + (" (needs the Groq key)" if not llm.groq_available() else f": {llm.last_error}"))
    specs = list(data.get("specs") or [])
    for k in ("serial", "year"):
        if data.get(k):
            specs.insert(0, {"label": "Serial number" if k == "serial" else "Year", "value": str(data[k])})
    data["specs"] = specs
    return _clean_draft(industry, data, "Nameplate photo")


def _type_key(industry, typ):
    t = (typ or "").lower()
    known = {a.get("type_key"): a.get("type", "") for a in packs.assets(industry) if a.get("type_key")}
    for k, label in known.items():
        if k and (k in t or (label and label.lower() in t) or (t and t in k)):
            return k
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")[:20] or "general"


def _clean_draft(industry, d, source_ref):
    def lst(x, n):
        return [i for i in (x or []) if isinstance(i, dict)][:n]
    out = {"name": str(d.get("name") or "").strip()[:60], "maker": str(d.get("maker") or "").strip()[:60],
           "model": str(d.get("model") or "").strip()[:40], "type": str(d.get("type") or "").strip()[:30],
           "summary": str(d.get("summary") or "").strip()[:300],
           "specs": [{"label": str(s.get("label", ""))[:40], "value": str(s.get("value", ""))[:80]} for s in lst(d.get("specs"), 12)
                     if s.get("label") and s.get("value")],
           "components": [{"name": str(c.get("name", ""))[:60], "part_no": str(c.get("part_no") or "")[:30],
                           "every_days": _int(c.get("every_days"))} for c in lst(d.get("components"), 12) if c.get("name")],
           "faults": [{k: str(f.get(k) or "")[:300] for k in ("title", "code", "symptoms", "cause", "fix")}
                      for f in lst(d.get("faults"), 10) if f.get("title")],
           "service": [{"task": str(s.get("task", ""))[:160], "every_days": _int(s.get("every_days"))}
                       for s in lst(d.get("service"), 10) if s.get("task")],
           "warranty_months": _int(d.get("warranty_months")), "source_ref": source_ref[:300], "note": d.get("note", "")}
    out["type_key"] = _type_key(industry, out["type"])
    return out


def _int(x):
    try:
        return int(float(x)) if x not in (None, "") else None
    except Exception:
        return None


# ---------- saving ----------
def _can_edit(industry, role_id):
    r = packs.role(industry, role_id)
    if not r or not r.get("can_approve"):
        raise PermissionError("Only a senior role can add or change machines. Workers can view them and use the QR sticker.")


def save(industry, d, person_id=None, role_id=None):
    _can_edit(industry, role_id)
    pk = packs.get(industry)
    aid = re.sub(r"[^A-Z0-9-]", "", str(d.get("id") or "").upper())[:14]
    if len(aid) < 2:
        raise ValueError(f"Give the {pk['labels']['asset'].lower()} a short ID, e.g. CNC-4 or FRY-2")
    if not (d.get("name") or "").strip():
        raise ValueError("Please give it a name")
    site_ids = [s["id"] for s in pk.get("sites", [])]
    site = d.get("site") if d.get("site") in site_ids else (site_ids[0] if site_ids else "")
    existing = packs.asset(industry, aid)
    is_new = existing is None
    new_service = [x for x in (d.get("service") or []) if isinstance(x, dict) and x.get("task")][:12]
    if not is_new and d.get("is_new"):
        raise ValueError(f"{aid} already exists — pick another ID, or open {aid} and edit it")
    install = (d.get("install_date") or "")[:10]
    warranty_until = (d.get("warranty_until") or "")[:10]
    if not warranty_until and install and _int(d.get("warranty_months")):
        try:
            w = datetime.fromisoformat(install) + timedelta(days=round(_int(d["warranty_months"]) * 30.44))
            warranty_until = w.date().isoformat()
        except Exception:
            pass
    comps = []
    for c in d.get("components") or []:
        if isinstance(c, dict) and c.get("name"):
            comps.append({"name": str(c["name"])[:60], "part_no": str(c.get("part_no") or "")[:30],
                          "every_days": _int(c.get("every_days")), "stock": _int(c.get("stock")),
                          "min_stock": _int(c.get("min_stock")) if c.get("min_stock") not in (None, "") else 1})
    row = {"id": aid, "name": d["name"].strip()[:60], "model": (d.get("model") or "").strip()[:40] or (existing or {}).get("model", ""),
           "type": (d.get("type") or "").strip()[:30] or (existing or {}).get("type", ""),
           "type_key": d.get("type_key") or (existing or {}).get("type_key") or _type_key(industry, d.get("type")),
           "site": site if is_new else (d.get("site") or existing.get("site")), "maker": (d.get("maker") or "").strip()[:60],
           "install_date": install, "warranty_until": warranty_until, "vendor": (d.get("vendor") or "").strip()[:80],
           "vendor_phone": re.sub(r"[^0-9+ ]", "", d.get("vendor_phone") or "")[:20],
           "summary": (d.get("summary") or "").strip()[:300],
           "specs": [s for s in (d.get("specs") or []) if isinstance(s, dict) and s.get("label")][:15],
           "components": comps, "service": _merge_service((existing or {}).get("service"), new_service),
           "source_ref": (d.get("source_ref") or "")[:300], "custom": is_new or bool((existing or {}).get("custom")),
           "added_by": person_id or "", "template": d.get("template") or (existing or {}).get("template") or "",
           "spec_fields": _clean_fields(d.get("spec_fields")) or (existing or {}).get("spec_fields") or [],
           "image": (d.get("image") or (existing or {}).get("image") or "")[:400],
           **{k: (existing or {}).get(k) for k in ("report", "universal", "part_tree", "report_meta", "serial_no")
              if (existing or {}).get(k)}}
    store.save_machine(industry, row, person_id or "")
    b = reader.recall_bundle(d.get("read_id"))
    if b:  # keep every page of the manual (bronze) and mark the ones used (silver) — for "ask the manual"
        pages, size = [], 0
        for pg in b["pages"]:
            if pg["text"] and size < 400_000:
                src_ref = b["sources"][pg["src"]]["ref"]
                pages.append({"source": str(src_ref), "page": pg["n"], "text": pg["text"], "kept": pg.get("kept"), "via": pg["via"]})
                size += len(pg["text"])
        store.save_manual_pages(industry, aid, pages)
    # the manual's knowledge goes into memory (and Hindsight)
    mems = []
    src = row["source_ref"] or "Maker's manual"
    for f in d.get("faults") or []:
        if isinstance(f, dict) and f.get("title"):
            title = f["title"] + (f" (code {f['code']})" if f.get("code") and f["code"] not in f["title"] else "")
            text = ". ".join(x for x in [f"Symptoms: {f['symptoms']}" if f.get("symptoms") else "",
                                         f"Cause: {f['cause']}" if f.get("cause") else "",
                                         f"Manual says: {f['fix']}" if f.get("fix") else ""] if x)
            mems.append(store.add_manual_item(industry, aid, "fault", title, text or title, src))
    for s in new_service:
        every = _int(s.get("every_days"))
        mems.append(store.add_manual_item(industry, aid, "service", s["task"],
                                          f"Do this every {every} days." if every else "Regular maintenance task.", src))
    new_source = row["source_ref"] and row["source_ref"] != (existing or {}).get("source_ref")
    if row["specs"] and (is_new or new_source):
        mems.append(store.add_manual_item(industry, aid, "spec", f"{row['name']} spec sheet",
                                          "; ".join(f"{s['label']}: {s['value']}" for s in row["specs"]), src))
    for f in d.get("parts_found") or []:  # part numbers read from a parts list or drawing
        if isinstance(f, dict) and f.get("name") and f.get("part_no") and len(mems) < 40:
            mems.append(store.add_manual_item(industry, aid, "part", f"{f['name']} — part no. {f['part_no']}",
                                              f"Spare part for {aid}: {f['name']}, part number {f['part_no']}.", src))
    where = memory.retain_many(industry, [manual_to_memory(industry, m) for m in mems]) if mems else "—"
    if b or is_new:  # new manual or new machine -> the expert read starts in the background
        from . import expert
        expert.start(industry, aid)
    return {"asset": packs.asset(industry, aid), "manual_memories": len(mems), "saved_to": where,
            "message": (f"✔ {aid} added." if is_new else f"✔ {aid} updated.")
            + (f" {len(mems)} manual facts saved to memory." if mems else "")}


def _clean_fields(fields):
    out = []
    for f in fields or []:
        if isinstance(f, dict) and f.get("key") and str(f.get("value") or "").strip():
            out.append({k: f.get(k) for k in ("key", "label", "unit", "value", "unit_given", "std", "status", "quote", "where", "note")})
    return out[:30]


# ---------- read anything + expert fill ----------
def read_source(industry, url=None, file=None, text=None, pages=None, read_id=None, model=None):
    """Paste a link, upload a PDF or a photo, or type text -> a checked draft for the 'add machine' form."""
    b = reader.recall_bundle(read_id) if read_id else None
    if b is None:
        if file:
            data, name, mime = file
            if (mime or "").startswith("image/"):
                import base64
                b = reader.read_photo(base64.b64encode(data).decode(), mime, name)
            else:
                b = reader.read_pdf(data, f"PDF: {name}", pages)
        elif url:
            b = reader.read_url(url, pages_hint=pages)
        elif (text or "").strip():
            if len(text.strip()) < 40:
                raise ValueError("Paste a bit more text, a link, or upload the manual.")
            b = reader.read_text(text)
        else:
            raise ValueError("Paste a link, upload a PDF or photo, or type the details.")
    ident = b.get("ident") or specs.identify(industry, b)
    b["ident"] = ident
    tpl, data = specs.extract(industry, b, ident, model)
    check = specs.verify(b, tpl, data)
    by_key = {f["key"]: f for f in check["fields"]}
    spec_list = [{"label": f["label"], "value": specs.show(f)} for f in check["fields"] if f["value"]]
    spec_list += [{"label": e["label"], "value": e["value"]} for e in check["extra"]]
    src = b["sources"][0] if b["sources"] else {"ref": ""}
    draft = _clean_draft(industry, {
        "name": _nice_name(ident.get("model_family") or b.get("title") or "", tpl["label"], model or ident.get("exact_model") or ""),
        "maker": ident.get("maker") or "",
        "model": model or ident.get("exact_model") or "", "type": tpl["label"], "summary": ident.get("summary") or "",
        "specs": spec_list, "components": data.get("components"), "faults": data.get("faults"), "service": data.get("service"),
        "warranty_months": data.get("warranty_months"), "note": data.get("note", "")}, str(src.get("ref") or ""))
    draft["specs"] = spec_list[:20]
    parts_found = [{"name": x["name"].title(), "part_no": x["part_no"], "info": x.get("info", ""), "where": x["where"]}
                   for x in b.get("parts") or []]
    draft.update({"read_id": b["id"], "read": reader.summary(b), "template": tpl["key"], "template_label": tpl["label"],
                  "spec_fields": check["fields"], "spec_extra": check["extra"], "spec_counts": check["counts"],
                  "spec_score": check["score"], "models": ident.get("models") or [], "chosen_model": model or "",
                  "image": reader.summary(b).get("image") or "", "parts_found": parts_found[:20],
                  "shown": {k: specs.show(f) for k, f in by_key.items()}})
    return draft


GENERIC_TITLE = re.compile(r"^\W*(user'?s?|owner'?s?|operat\w*|instruction\w*|service|installation|maintenance|technical)?\s*"
                           r"(manual|guide|handbook|instructions|datasheet|data sheet|spec(ification)?s?( sheet)?)\W*$|^typed in$", re.I)


def _nice_name(name, kind, model):
    """'USER MANUAL' (a cover page) is not a machine name: use 'Fryer 351FCPG30N' instead."""
    name = re.sub(r"\s+", " ", name or "").strip()
    if not name or GENERIC_TITLE.match(name) or len(name) > 70:
        return " ".join(x for x in (kind if kind != "General" else "", model) if x) or name[:70]
    return name


def ask_manual(industry, aid, question):
    """Answer from this machine's own manual pages, with the page number for every claim."""
    import math
    from collections import Counter
    from .memory import _tokens
    a = packs.asset(industry, aid)
    if not a:
        raise ValueError("Unknown item")
    question = (question or "").strip()[:500]
    if not question:
        raise ValueError("Type a question about the manual")
    pages = store.manual_pages(industry, aid)
    if not pages:
        raise ValueError(f"No manual stored for {aid} yet. Add one with ✏️ Edit details → PDF or web link.")
    drawing = drawing_search(pages, question)
    docs = [set(_tokens(p["text"])) for p in pages]
    df = Counter(w for d in docs for w in d)
    q = set(_tokens(question))
    codes = {c for c in re.findall(r"\d{3,}", question)}
    scored = []
    for p, d in zip(pages, docs):
        sc = sum(math.log(1 + len(docs) / df[w]) for w in q if w in d) + (6 if any(c in p["text"] for c in codes) else 0)
        if sc > 0:
            scored.append((sc, p))
    top = [p for _, p in sorted(scored, key=lambda x: -x[0])[:4]]
    hit_pages = {(h["source"], h["page"]) for h in drawing}
    top = [p for p in pages if (p["source"], p["page"]) in hit_pages][:2] + [p for p in top if (p["source"], p["page"]) not in hit_pages]
    top = top[:4]
    if not top:
        return {"answer": "The stored manual pages don't mention that. Try other words, or check the full manual.", "pages": [],
                "refs": [], "drawing": [], "written_by": "search"}
    refs = [{"page": p["page"], "src": _src_id(p["source"]), "label": f"{reader._short(p['source'])} p.{p['page']}"} for p in top]
    cite = lambda p: f"{reader._short(p['source'])} p.{p['page']}"  # noqa: E731
    ctx = "\n\n".join(f"[{cite(p)}]\n{p['text'][:2500]}" for p in top)
    data = llm.chat_json(
        "You answer a technician's question using ONLY the manual pages given. Cite the page for every fact like (p.45). "
        "If the pages don't answer it, say so plainly. Short and practical. Never invent values.",
        f"Machine: {aid} — {a.get('name', '')}\nQuestion: {question}\n\nMANUAL PAGES:\n{ctx}\n\n"
        "Return ONLY JSON: {\"answer\": \"2-5 sentences with (p.N) citations\", \"steps\": [\"if it is a procedure\"]}",
        max_tokens=900) if llm.available() else None
    if isinstance(data, dict) and data.get("answer"):
        return {"answer": data["answer"], "steps": data.get("steps") or [], "pages": [cite(p) for p in top], "refs": refs,
                "drawing": drawing, "written_by": llm.last_provider or "AI"}
    best = top[0]
    snippet = re.sub(r"\s+", " ", best["text"])[:600]
    return {"answer": f"From {cite(best)}: {snippet}…", "steps": [], "pages": [cite(p) for p in top], "refs": refs,
            "drawing": drawing, "written_by": "search (no AI key)"}


# ---------- drawings, pages, photo -> pages ----------
TAG = re.compile(r"\b(?:[A-Z]{1,4}\d{1,4}[A-Z]?(?::\d{1,3})?|[A-Z]{2,5}-\d{1,4}[A-Z]?)\b")


def _src_id(source):
    import hashlib
    return hashlib.md5((source or "").encode()).hexdigest()[:8]


def drawing_search(pages, question):
    """'Where is relay K1?' -> every page where the tag K1 appears (wiring diagrams, pipe drawings, parts drawings),
    with the words around it. Works on drawings that have text, and on pages read by Sarvam Vision."""
    tags = [t for t in dict.fromkeys(TAG.findall(question or "")) if not re.fullmatch(r"[A-Z]+\d{3,}", t) or ":" in t][:4]
    tags += [t for t in re.findall(r"\b[A-Z]{1,3}\d{1,3}\b", question or "") if t not in tags][:2]
    out = []
    for t in tags:
        pat = re.compile(r"(?<![A-Za-z0-9])" + re.escape(t) + r"(?![A-Za-z0-9])")
        for p in pages:
            m = pat.search(p["text"])
            if not m:
                continue
            tag_count = len(TAG.findall(p["text"]))
            ctx = re.sub(r"\s+", " ", p["text"][max(0, m.start() - 90): m.end() + 90]).strip()
            out.append({"tag": t, "page": p["page"], "source": p["source"], "src": _src_id(p["source"]),
                        "label": f"{reader._short(p['source'])} p.{p['page']}", "context": ctx,
                        "drawing": tag_count >= 15, "times": len(pat.findall(p["text"]))})
    out.sort(key=lambda h: (not h["drawing"], -h["times"]))
    return out[:6]


def manual_page(industry, aid, page, src=None):
    pages = [p for p in store.manual_pages(industry, aid) if p["page"] == int(page) and (not src or _src_id(p["source"]) == src)]
    if not pages:
        raise ValueError("That page isn't stored for this machine")
    p = pages[0]
    return {"page": p["page"], "source": reader._short(p["source"]), "src": _src_id(p["source"]), "text": p["text"],
            "via": p.get("via", "text")}


def photo_pages(industry, aid, image_bytes, mime):
    """A photo of a panel, label or part -> the manual pages that match it (Sarvam Vision reads the photo's text)."""
    import base64
    import math
    from collections import Counter
    from . import ocr
    from .memory import _tokens
    pages = store.manual_pages(industry, aid)
    if not pages:
        raise ValueError(f"No manual stored for {aid} yet")
    text, by = (ocr.image_text(image_bytes, mime), "Sarvam Vision") if ocr.available() else (None, None)
    if not text:
        seen = llm.read_photo(base64.b64encode(image_bytes).decode(), mime, "machine part or panel")
        text = " ".join([seen.get("what_i_see", "")] + seen.get("codes", []) + seen.get("readings", [])) if isinstance(seen, dict) else ""
        by = "Groq vision (backup)" if text else None
    if not text:
        raise ValueError("Couldn't read any text in the photo — try a closer, sharper photo")
    q = set(_tokens(text))
    tags = set(TAG.findall(text)) | set(re.findall(r"\d{3,}", text))
    docs = [set(_tokens(p["text"])) for p in pages]
    df = Counter(w for d in docs for w in d)
    scored = []
    for p, d in zip(pages, docs):
        sc = sum(math.log(1 + len(docs) / df[w]) for w in q if w in d) + 4 * sum(1 for t in tags if t in p["text"])
        if sc > 0:
            scored.append((sc, p))
    top = [p for _, p in sorted(scored, key=lambda x: -x[0])[:3]]
    return {"read": text[:400], "read_by": by,
            "pages": [{"page": p["page"], "src": _src_id(p["source"]), "label": f"{reader._short(p['source'])} p.{p['page']}",
                       "snippet": re.sub(r"\s+", " ", p["text"])[:220]} for p in top]}


def similar(industry, a):
    """Machines like this one: same kind, and the same maker / model family or close key specs."""
    mine = {f["key"]: f for f in a.get("spec_fields") or []}
    tkey = a.get("template") or specs.guess_type(a.get("type", ""), a.get("type_key"))
    out = []
    for o in packs.assets(industry):
        if o["id"] == a["id"]:
            continue
        okey = o.get("template") or specs.guess_type(o.get("type", ""), o.get("type_key"))
        if okey != tkey:
            continue
        why = []
        if a.get("model") and o.get("model") == a.get("model"):
            why.append("same model")
        elif a.get("maker") and o.get("maker") and a["maker"].split()[0].lower() == o["maker"].split()[0].lower():
            why.append(f"same maker ({o['maker']})")
        theirs = {f["key"]: f for f in o.get("spec_fields") or []}
        close = [mine[k]["label"] for k in mine if k in theirs and isinstance(mine[k].get("std"), (int, float))
                 and isinstance(theirs[k].get("std"), (int, float)) and mine[k]["std"]
                 and abs(mine[k]["std"] - theirs[k]["std"]) / abs(mine[k]["std"]) <= 0.15]
        if len(close) >= 2:
            why.append("close specs: " + ", ".join(close[:3]))
        if why or not mine:
            out.append({"id": o["id"], "name": o.get("name", ""), "site": o.get("site"), "why": "; ".join(why) or "same kind of machine"})
    return out[:6]


def service_ics(industry, aid):
    a = packs.asset(industry, aid)
    if not a:
        raise ValueError("Unknown item")
    now = datetime.now().strftime("%Y%m%dT%H%M%SZ")
    ev = []
    for i, x in enumerate(service_due(industry, a)):
        d = x["next"].replace("-", "")
        ev.append("\r\n".join(["BEGIN:VEVENT", f"UID:ustaad-{industry}-{aid}-{i}-{d}@ustaad", f"DTSTAMP:{now}",
                                 f"DTSTART;VALUE=DATE:{d}", f"RRULE:FREQ=DAILY;INTERVAL={x['every_days']};COUNT=12",
                                 f"SUMMARY:{aid}: {x['what'][:80]}",
                                 f"DESCRIPTION:Every {x['every_days']} days. From Ustaad (My machines).",
                                 "BEGIN:VALARM", "TRIGGER:-P1D", "ACTION:DISPLAY", "DESCRIPTION:Service due tomorrow", "END:VALARM",
                                 "END:VEVENT"]))
    return "\r\n".join(["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Ustaad//Service//EN", *ev, "END:VCALENDAR"]) + "\r\n"


def _merge_service(old, new):
    out, seen = [], set()
    for x in list(old or []) + list(new or []):
        if isinstance(x, dict) and x.get("task") and x["task"].lower() not in seen:
            seen.add(x["task"].lower())
            out.append({"task": x["task"][:160], "every_days": _int(x.get("every_days"))})
    return out[:15]


def set_stock(industry, aid, part, stock):
    a = packs.asset(industry, aid)
    if not a:
        raise ValueError("Unknown item")
    row = next((m for m in store.machines(industry) if m["id"] == aid), None) or {"id": aid}
    comps = [dict(c) for c in (row.get("components") or a.get("components") or [])]
    hit = next((c for c in comps if c["name"] == part), None)
    if not hit:
        raise ValueError("Unknown part")
    hit["stock"] = max(0, _int(stock) or 0)
    store.save_machine(industry, {**row, "components": comps})
    return {"ok": True, "part": hit}


def use_parts(industry, aid, text):
    """When a repair log says a part was replaced, take one off the store's stock."""
    a = packs.asset(industry, aid)
    t = (text or "").lower()
    if not a or not a.get("components") or not re.search(r"replac|chang|new |fitted|install|swap|refill|topped|added", t):
        return []
    row = next((m for m in store.machines(industry) if m["id"] == aid), None) or {"id": aid}
    comps = [dict(c) for c in (row.get("components") or a.get("components"))]
    used = []
    for c in comps:
        words = [w for w in re.findall(r"[a-z0-9]+", c["name"].lower()) if len(w) > 3][:2]
        if words and all(w in t for w in words) and c.get("stock") not in (None, ""):
            was = int(c["stock"])
            c["stock"] = max(0, was - 1)
            used.append({"name": c["name"], "stock": c["stock"], "was_zero": was <= 0})
    if used:
        store.save_machine(industry, {**row, "components": comps})
    return used


# ---------- profile ----------
OUTCOME = {"fixed": "Worked", "failed_again": "Didn't work", "temporary": "Temporary", "open": "Open"}


def _last_done(recs, name):
    words = [w for w in re.findall(r"[a-z0-9]+", (name or "").lower()) if len(w) > 3][:2]
    if not words:
        return None
    hits = [r for r in recs if all(w in f"{r.get('action', '')} {r.get('parts', '')}".lower() for w in words)]
    return hits[-1]["datetime"][:10] if hits else None


def _due(base, every, today, from_history):
    """Next due date. From repair history: last time + interval (can be overdue).
    From the install date only: the next cycle from today (we don't know if earlier cycles were done)."""
    if not base or not every:
        return None
    try:
        b = date.fromisoformat(base[:10])
    except Exception:
        return None
    if from_history or b >= today:
        return b + timedelta(days=every)
    n = -(-(today - b).days // every)
    return b + timedelta(days=every * max(n, 1))


def service_due(industry, a, recs=None, today=None):
    today = today or date.today()
    recs = recs if recs is not None else [r for r in store.records(industry, a["id"]) if r["status"] != "rejected"]
    items = []
    for c in a.get("components") or []:
        if not c.get("every_days"):
            continue
        last = _last_done(recs, c["name"])
        base = last or a.get("install_date")
        nxt = _due(base, c["every_days"], today, bool(last))
        if nxt:
            left = (nxt - today).days
            items.append({"what": f"Replace / check {c['name']}", "every_days": c["every_days"], "last_done": last,
                          "last_from": "repair history" if last else ("install date" if base else ""),
                          "next": nxt.isoformat(), "days_left": left,
                          "status": "overdue" if left < 0 else ("soon" if left <= 7 else "ok")})
    for s in a.get("service") or []:
        every = _int(s.get("every_days"))
        if every and every >= 7 and a.get("install_date"):
            nxt = _due(a["install_date"], every, today, False)
            if nxt:
                left = (nxt - today).days
                items.append({"what": s["task"], "every_days": every, "last_done": None, "last_from": "install date",
                              "next": nxt.isoformat(), "days_left": left, "status": "soon" if left <= 7 else "ok"})
    return sorted(items, key=lambda x: x["days_left"])


def parts(a):
    out = []
    for c in a.get("components") or []:
        st = c.get("stock")
        status = "unknown" if st in (None, "") else ("out" if int(st) <= 0 else ("low" if int(st) <= int(c.get("min_stock") or 1) else "ok"))
        out.append({**c, "status": status})
    return out


def health(industry, a, recs=None, today=None):
    """Green / amber / red with plain reasons."""
    today = today or date.today()
    recs = recs if recs is not None else [r for r in store.records(industry, a["id"]) if r["status"] != "rejected"]
    reasons, level = [], 0
    if recs and recs[-1]["outcome"] in ("open", "failed_again"):
        level = 2
        reasons.append(f"Last problem not solved yet: {recs[-1]['problem']}")
    recent = [r for r in recs if (today - date.fromisoformat(r["datetime"][:10])).days <= 90]
    if len(recent) >= 3:
        level = max(level, 1)
        reasons.append(f"{len(recent)} problems in the last 90 days")
    due = service_due(industry, a, recs, today)
    over = [x for x in due if x["status"] == "overdue"]
    if over:
        level = max(level, 1 if len(over) == 1 else 2)
        reasons.append(f"{len(over)} service item(s) overdue")
    out = [p for p in parts(a) if p["status"] == "out"]
    if out:
        level = max(level, 1)
        reasons.append(f"Out of stock: {', '.join(p['name'] for p in out[:2])}")
    if a.get("warranty_until"):
        try:
            left = (date.fromisoformat(a["warranty_until"]) - today).days
            if 0 <= left <= 45:
                reasons.append(f"Warranty ends in {left} days")
        except Exception:
            pass
    return {"level": ["green", "amber", "red"][level], "label": ["Healthy", "Needs attention", "Problem now"][level],
            "reasons": reasons or ["No open problems, nothing overdue"]}


def _experts(industry, a, recs_all):
    twins = {x["id"] for x in packs.assets(industry) if x.get("model") and x.get("model") == a.get("model")} | {a["id"]}
    count = {}
    for r in recs_all:
        if r["asset_id"] in twins and r["outcome"] == "fixed" and r["status"] != "rejected" and packs.person(industry, r["person_id"]):
            count[r["person_id"]] = count.get(r["person_id"], 0) + 1
    out = []
    for pid, n in sorted(count.items(), key=lambda kv: -kv[1])[:3]:
        p = packs.person(industry, pid)
        out.append({"person_id": pid, "name": p["name"], "role": p.get("role", ""), "fixes": n, "leaving": p.get("retiring_on")})
    return out


def best_expert(industry, aid, problem="", exclude=None):
    a = packs.asset(industry, aid)
    if not a:
        return None
    recs = [r for r in store.records(industry) if r["status"] != "rejected"]
    same = [r for r in recs if r["problem"] == problem and r["outcome"] == "fixed"]
    count = {}
    for r in same:
        if r["person_id"] != exclude and packs.person(industry, r["person_id"]):
            count[r["person_id"]] = count.get(r["person_id"], 0) + 1
    if count:
        pid = max(count, key=count.get)
        p = packs.person(industry, pid)
        return {"person_id": pid, "name": p["name"], "role": p.get("role", ""), "fixes": count[pid], "about": problem}
    ex = [e for e in _experts(industry, a, recs) if e["person_id"] != exclude]
    return ({**ex[0], "about": a["id"]} if ex else None)


def summary_list(industry):
    today = date.today()
    out = []
    for a in packs.assets(industry):
        recs = [r for r in store.records(industry, a["id"]) if r["status"] != "rejected"]
        due = service_due(industry, a, recs, today)
        out.append({**{k: a.get(k) for k in ("id", "name", "model", "type", "site", "maker", "custom")},
                    "health": health(industry, a, recs, today), "problems": len(recs),
                    "fixed": sum(1 for r in recs if r["outcome"] == "fixed"),
                    "due_soon": sum(1 for x in due if x["status"] in ("soon", "overdue")),
                    "parts_low": sum(1 for p in parts(a) if p["status"] in ("low", "out")),
                    "manual": len(store.manual_items(industry, a["id"]))})
    return out


def profile(industry, aid):
    a = packs.asset(industry, aid)
    if not a:
        raise ValueError("Unknown item")
    today = date.today()
    recs_all = [r for r in store.records(industry) if r["status"] != "rejected"]
    recs = [r for r in recs_all if r["asset_id"] == aid]
    site = packs.site(industry, a.get("site")) or {}
    twins = [x["id"] for x in packs.assets(industry) if x.get("model") and x.get("model") == a.get("model") and x["id"] != aid]
    history = [{"key": r["id"], "date": r["datetime"][:10], "problem": r["problem"], "action": r["action"], "cause": r["cause"],
                "outcome": r["outcome"], "outcome_label": OUTCOME.get(r["outcome"], r["outcome"]),
                "person": (packs.person(industry, r["person_id"]) or {}).get("name") or r["person_id"] or "",
                "minutes": r["downtime_minutes"], "status": r["status"], "source": r.get("source"),
                "sensor": store.meta_get(f"sensor:{r['id']}")} for r in reversed(recs)][:40]
    warranty = None
    if a.get("warranty_until"):
        try:
            left = (date.fromisoformat(a["warranty_until"]) - today).days
            warranty = {"until": a["warranty_until"], "days_left": left, "active": left >= 0}
        except Exception:
            pass
    return {"asset": a, "site": site.get("name", ""), "twins": twins, "health": health(industry, a, recs, today),
            "service_due": service_due(industry, a, recs, today), "parts": parts(a), "warranty": warranty,
            "history": history, "experts": _experts(industry, a, recs_all),
            "manual": [{"key": m["id"], "kind": m["kind"], "title": m["title"], "text": m["text"], "source": m["source_ref"]}
                       for m in store.manual_items(industry, aid)],
            "stats": {"problems": len(recs), "fixed": sum(1 for r in recs if r["outcome"] == "fixed"),
                      "hours_lost": round(sum(r["downtime_minutes"] or 0 for r in recs) / 60, 1),
                      "last_problem": recs[-1]["datetime"][:10] if recs else None},
            "sensor": sensor_state(industry, aid), "similar": similar(industry, a),
            "spec_fields": [{**f, "shown": specs.show(f)} for f in a.get("spec_fields") or []],
            "manual_pages": len(store.manual_pages(industry, aid)), **_smart(industry, a)}


def _smart(industry, a):
    from . import diagnosis
    lim = diagnosis.maker_limits(a)
    return {"uptime": diagnosis.uptime(industry, a["id"]), "part_life": diagnosis.part_life(industry, a),
            "hour_meter": (diagnosis.hour_meter(industry, a["id"]) or [None])[-1], "cost": diagnosis.cost_incidents(industry, a["id"], 5),
            "maker_limits": {k: v["text"] for k, v in lim.items()}, "stop_reasons": diagnosis.STOP_REASONS}


# ---------- sensors: auto-log and sensor-confirmed fixes ----------
def _thresholds():
    s = packs.processed("factory_sensors.json") or {}
    th = s.get("thresholds") or {}
    return {"vib_warn": th.get("vib_warn", 4.5), "temp_warn": th.get("temp_warn", 80)}


def _open_sensor_log(industry, aid, hours=24):
    for r in reversed(store.records(industry, aid)):
        if r.get("source") == "sensor" and r["outcome"] == "open":
            try:
                if datetime.now() - datetime.fromisoformat(store.meta_get(f"sensorlog:{r['id']}").get("created", "2000-01-01T00:00")) \
                        <= timedelta(hours=hours):
                    return r
            except Exception:
                return r
    return None


def sensor_alert(industry, aid, reading):
    """A sensor crossed its limit: open a half-filled log by itself (once per few hours per machine)."""
    a = packs.asset(industry, aid)
    if not a:
        raise ValueError("Unknown item")
    existing = _open_sensor_log(industry, aid, hours=6)
    if existing:
        st = store.meta_get(f"sensorlog:{existing['id']}") or {}
        return {"record": existing, "new": False, "plan": st.get("plan"),
                "message": f"Already logged as open issue {existing['id']}."}
    vib, temp = reading.get("vib"), reading.get("temp")
    th, lim = _limits(a)
    what = "High vibration" if vib is not None and float(vib) >= th["vib_warn"] else "High temperature"
    plan = alert_plan(industry, a, what, reading, th)
    limit_text = (lim.get("vib") if what == "High vibration" else lim.get("temp") or {}) or {}
    rec = store.add_record(industry, {
        "asset_id": aid, "person_id": "sensor", "problem": f"Sensor alert: {what.lower()}", "code": "",
        "symptom": f"Sensor reading: vibration {vib} mm/s, temperature {temp} °C" + (f" at {reading['time']}" if reading.get("time") else "")
                   + (f". Maker's limit: {limit_text['text']}" if limit_text.get("text") else ""),
        "cause": "", "action": "Auto-logged by the sensor — waiting for a technician", "outcome": "open",
        "status": "approved", "source": "sensor", "notes": "Created automatically when the sensor crossed its limit."})
    store.meta_set(f"sensorlog:{rec['id']}", {"created": datetime.now().isoformat(timespec="minutes"), "reading": reading, "plan": plan})
    memory.retain(industry, record_to_memory(industry, rec))
    who = plan["expert"]["name"].split()[0] if plan.get("expert") else None
    return {"record": rec, "new": True, "plan": plan,
            "message": f"📝 Auto-logged as open issue {rec['id']}" + (f" — {who} is the best person to call." if who else ".")}


def alert_plan(industry, a, what, reading, th=None):
    """🏭 The machine calls first: from the team's own records, guess what this alert usually is, who fixes it best,
    and what worked last time — so the right person is called before the breakdown."""
    th = th or _limits(a)[0]
    keys = ("vibrat",) if what == "High vibration" else ("temp", "hot", "heat", "overheat", "thermal")
    twins = {x["id"] for x in packs.assets(industry) if x.get("model") and x.get("model") == a.get("model")} | {a["id"]}
    recs = [r for r in store.records(industry) if r["asset_id"] in twins and r["status"] != "rejected" and r.get("source") != "sensor"]
    like = [r for r in recs if any(k in f"{r['problem']} {r.get('symptom', '')} {r.get('cause', '')}".lower() for k in keys)]
    count = {}
    for r in like:
        count[r["problem"]] = count.get(r["problem"], 0) + 1
    problem = max(count, key=count.get) if count else ""
    # who to call: own fixes of this problem + fixes of theirs others reused, and someone at the same site counts double
    score, own, reused = {}, {}, {}
    for r in store.records(industry):
        if r["status"] == "rejected" or r["outcome"] != "fixed" or (problem and r["problem"] != problem):
            continue
        for pid, bucket in ((r.get("person_id"), own), (r.get("credited_to"), reused)):
            p = packs.person(industry, pid) if pid else None
            if p:
                bucket[pid] = bucket.get(pid, 0) + 1
                score[pid] = score.get(pid, 0) + (2 if p.get("site") == a.get("site") else 1)
    if score:
        pid = max(score, key=score.get)
        p = packs.person(industry, pid)
        expert = {"person_id": pid, "name": p["name"], "role": p.get("role", ""), "fixes": own.get(pid, 0),
                  "reused": reused.get(pid, 0), "about": problem}
    else:
        expert = best_expert(industry, a["id"])
    fixed = [r for r in like if r["outcome"] == "fixed" and (not problem or r["problem"] == problem)]
    last = fixed[-1] if fixed else None
    p = packs.person(industry, expert["person_id"]) if expert else None
    value = f"{reading.get('vib')} mm/s (limit {th['vib_warn']})" if what == "High vibration" else f"{reading.get('temp')} °C (limit {th['temp_warn']})"
    nm = a.get("name", "")
    nm = nm[len(a["id"]):].lstrip(" ·:—-") if nm.startswith(a["id"]) else nm
    msg = (f"{expert['name'].split()[0]} ji, Ustaad alert: {a['id']} ({nm}) — {what.lower()}, {value}."
           + (f" Last time this was '{problem}' and this worked: {last['action'][:120]}." if last else "")
           + " Can you come and check before it breaks down?") if expert else ""
    return {"what": what, "value": value, "likely_problem": problem, "expert": expert, "phone": (p or {}).get("phone"),
            "last_fix": {"date": last["datetime"][:10], "action": last["action"], "asset_id": last["asset_id"]} if last else None,
            "message": msg}


def open_alerts(industry, hours=24):
    """Machines that called in the last day and are still waiting for someone."""
    out = []
    for r in store.records(industry):
        if r.get("source") != "sensor" or r["outcome"] != "open":
            continue
        st = store.meta_get(f"sensorlog:{r['id']}") or {}
        try:
            age = (datetime.now() - datetime.fromisoformat(st.get("created", ""))).total_seconds() / 60
        except ValueError:
            continue
        if age > hours * 60:
            continue
        a = packs.asset(industry, r["asset_id"]) or {}
        plan = st.get("plan") or alert_plan(industry, a, "High vibration" if "vibration" in r["problem"] else "High temperature",
                                            st.get("reading") or {})
        out.append({"id": r["id"], "asset_id": r["asset_id"], "name": a.get("name", ""), "minutes_ago": round(age),
                    "reading": st.get("reading") or {}, **plan})
    return sorted(out, key=lambda x: x["minutes_ago"])


def close_sensor_log(industry, aid, outcome, person_id, action, cause, minutes, problem=None):
    """When a worker reports the result for a machine with an open sensor log, finish that log instead of making a new one."""
    r = _open_sensor_log(industry, aid)
    if not r:
        return None
    store.update_record(r["id"], {"outcome": outcome, "person_id": person_id, "action": action, "cause": cause,
                                  "problem": problem or r["problem"],
                                  "downtime_minutes": float(minutes or 0),
                                  "notes": (r.get("notes") or "") + " Finished by the technician through Ustaad."})
    if outcome == "fixed":
        store.meta_set(f"sensor:{r['id']}", {"awaiting": True, "since": datetime.now().isoformat(timespec="minutes")})
    rec = store.record(r["id"])
    memory.retain(industry, record_to_memory(industry, rec))
    return rec


def _limits(a):
    """Default sensor limits, replaced by the maker's own limits when the manual gives them."""
    from . import diagnosis
    th, lim = dict(_thresholds()), diagnosis.maker_limits(a or {})
    if lim.get("temp"):
        th["temp_warn"] = lim["temp"]["max"]
    if lim.get("vib"):
        th["vib_warn"] = lim["vib"]["max"]
    return th, lim


def sensor_reading(industry, aid, vib, temp, hours=None):
    """Live readings API (a factory's sensor gateway can post here). Three normal readings after a fix -> sensor-confirmed.
    The limits are the maker's own when the manual gives them. An hour-meter value can come along too."""
    a = packs.asset(industry, aid)
    if not a:
        raise ValueError("Unknown item")
    th, lim = _limits(a)
    if hours not in (None, ""):
        from . import diagnosis
        try:
            diagnosis.log_hours(industry, aid, hours)
        except ValueError:
            pass
    key = f"readings:{industry}:{aid}"
    hist = (store.meta_get(key).get("last") or [])[-9:] + [{"vib": float(vib), "temp": float(temp),
                                                            "at": datetime.now().isoformat(timespec="seconds")}]
    store.meta_set(key, {"last": hist})
    normal = len(hist) >= 3 and all(h["vib"] < th["vib_warn"] and h["temp"] < th["temp_warn"] for h in hist[-3:])
    confirmed = None
    if normal:
        for r in reversed(store.records(industry, aid)):
            st = store.meta_get(f"sensor:{r['id']}")
            if st.get("awaiting") and not st.get("confirmed"):
                st.update(confirmed=True, confirmed_at=datetime.now().isoformat(timespec="minutes"))
                store.meta_set(f"sensor:{r['id']}", st)
                confirmed = r["id"]
                break
    alert = None
    if hist[-1]["vib"] >= th["vib_warn"] or hist[-1]["temp"] >= th["temp_warn"]:
        alert = sensor_alert(industry, aid, {"vib": vib, "temp": temp})
    return {"ok": True, "normal": normal, "confirmed_record": confirmed, "alert": alert,
            "limits": {"temp": th["temp_warn"], "vib": th["vib_warn"], "from_maker": {k: v["text"] for k, v in lim.items()}}}


def sensor_state(industry, aid):
    recs = [r for r in store.records(industry, aid) if r.get("source") == "sensor"]
    if not recs:
        return None
    r = recs[-1]
    st = store.meta_get(f"sensor:{r['id']}")
    state = ("confirmed" if st.get("confirmed") else "waiting" if st.get("awaiting") else
             "open" if r["outcome"] == "open" else "closed")
    text = {"confirmed": "✔ Sensor-confirmed: readings went back to normal after the fix.",
            "waiting": "Fix reported. Waiting for normal readings from the sensor to confirm it.",
            "open": "Open: the sensor logged this problem. Waiting for a technician.",
            "closed": "Closed by the technician."}[state]
    return {"record": r["id"], "problem": r["problem"], "state": state, "text": text, "symptom": r["symptom"]}


# ---------- demo data for the built-in industries ----------
def load_demo(industry):
    path = config.ROOT / "data" / "demo_machines.json"
    if not path.exists():
        return 0
    rows = json.loads(path.read_text(encoding="utf-8")).get(industry, [])
    for row in rows:
        if packs.asset(industry, row["id"]) or row.get("custom"):
            store.save_machine(industry, {**row, "demo": True}, "demo")
    return len(rows)
