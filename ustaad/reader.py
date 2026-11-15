"""
Reader — turns anything a person pastes or uploads into a "source bundle" that remembers where every line came from.

  web page   -> exact spec tables, hidden product data (JSON-LD), clean text; JavaScript-only or blocked pages are
                read through a page-rendering service; "datasheet / brochure / manual" PDF links are followed (up to 3)
  PDF        -> text of every page (pypdf), real tables on the useful pages (pdfplumber), and picture-only pages
                (scans, parts drawings) turned into images and read by the vision AI
  photo      -> nameplate / rating plate / alarm screen read by the vision AI
  text       -> as typed

Layers (a "medallion" pipeline): bronze = every page's raw text, silver = the pages picked as useful,
gold = the checked facts that specs.py extracts. Every fact can be traced back to its page or table.
"""
import base64
import html as htmllib
import io
import ipaddress
import json
import re
import socket
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin, urlparse

import requests

from . import llm, ocr

INDIC_CHARS = re.compile(r"[\u0900-\u0DFF]")

UA = {"User-Agent": "Mozilla/5.0 (compatible; UstaadBot/1.0; reads product pages a user pasted)",
      "Accept-Language": "en-IN,en;q=0.8"}
JINA = "https://r.jina.ai/"
BUDGET = 11000          # characters of page text sent to the AI
MAX_DOWNLOAD = 15_000_000
VISION_PAGES = 6        # most picture-only pages read per document
USEFUL = re.compile(r"alarm|trouble|fault|error|maint|lubric|specif|technical|clean|filter|replac|inspect|warrant|daily|weekly|"
                    r"monthly|pressure|temperature|pilot|thermostat|service|parts? list|capacity|voltage|power|rpm|kw|bar|"
                    r"dimension|weight|model", re.I)
MUST = re.compile(r"specification|technical data|technische daten|alarm list|troubleshoot|trouble shoot|parts? list|"
                  r"parts diagram|maintenance schedule|daily maintenance|warranty|power requirement|rated|data sheet|datasheet", re.I)
DOC_LINK = re.compile(r"datasheet|data-sheet|data sheet|brochure|manual|catalog|catalogue|spec|technical|download|leaflet", re.I)

_cache, _lock = {}, threading.Lock()


# ---------- safety ----------
def check_url(url):
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


def _get(url, timeout=25):
    """GET a public URL, following redirects ourselves and checking every hop. Returns (final_url, content_type, bytes)."""
    url = check_url(url)
    for _ in range(5):
        r = requests.get(url, headers=UA, timeout=timeout, stream=True, allow_redirects=False)
        if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("location"):
            url = check_url(urljoin(url, r.headers["location"]))
            continue
        r.raise_for_status()
        return url, r.headers.get("content-type", ""), r.raw.read(MAX_DOWNLOAD, decode_content=True)
    raise ValueError("Too many redirects")


# ---------- bundle ----------
def new_bundle(title=""):
    return {"id": uuid.uuid4().hex[:12], "title": title, "sources": [], "pages": [], "rows": [], "product": {},
            "images": [], "notes": [], "created": time.time()}


def remember(b):
    with _lock:
        _cache[b["id"]] = b
        for k in sorted(_cache, key=lambda k: _cache[k]["created"])[:-30]:
            _cache.pop(k, None)
    return b


def recall_bundle(read_id):
    b = _cache.get(read_id or "")
    if b and time.time() - b["created"] < 3600:
        return b
    return None


def _add_page(b, src, n, text, via, kept=False):
    text = re.sub(r"[ \t ]+", " ", text or "").strip()
    text = re.sub(r"\n\s*\n+", "\n", text)
    b["pages"].append({"src": src, "n": n, "text": text, "via": via, "kept": kept})


# ---------- web ----------
def _cell(el):
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)).strip()


def _web_structured(soup, where):
    """Exact rows from spec tables and definition lists, plus hidden product data. No AI involved."""
    rows, product = [], {}
    for t in soup.find_all("table")[:25]:
        trs = t.find_all("tr")
        header = None
        for tr in trs[:80]:
            cells = [_cell(c) for c in tr.find_all(["th", "td"])]
            cells = [c for c in cells]
            if not any(cells):
                continue
            if header is None and len(cells) > 2 and (tr.find("th") is not None and not tr.find("td")):
                header = cells
                continue
            if len(cells) == 2 and cells[0] and cells[1]:
                rows.append({"label": cells[0][:80], "value": cells[1][:160], "where": where})
            elif len(cells) > 2 and cells[0]:
                if header and len(header) == len(cells):
                    val = "; ".join(f"{h}: {v}" for h, v in zip(header[1:], cells[1:]) if v)
                else:
                    val = " | ".join(c for c in cells[1:] if c)
                if val:
                    rows.append({"label": cells[0][:80], "value": val[:240], "where": where})
    for dl in soup.find_all("dl")[:20]:
        for dt in dl.find_all("dt"):
            dd = dt.find_next_sibling("dd")
            if dd and _cell(dt) and _cell(dd):
                rows.append({"label": _cell(dt)[:80], "value": _cell(dd)[:160], "where": where})
    for s in soup.find_all("script", attrs={"type": "application/ld+json"})[:10]:
        try:
            data = json.loads(s.string or "")
        except Exception:
            continue
        items = data if isinstance(data, list) else (data.get("@graph") or [data])
        for it in items:
            if not isinstance(it, dict):
                continue
            typ = it.get("@type")
            if "Product" in (typ if isinstance(typ, list) else [typ]):
                brand = it.get("brand")
                product = {"name": it.get("name"), "brand": brand.get("name") if isinstance(brand, dict) else brand,
                           "model": it.get("model") if isinstance(it.get("model"), str) else None,
                           "mpn": it.get("mpn"), "sku": it.get("sku"),
                           "description": (it.get("description") or "")[:600]}
                for p in it.get("additionalProperty") or []:
                    if isinstance(p, dict) and p.get("name") and p.get("value") is not None:
                        unit = p.get("unitText") or p.get("unitCode") or ""
                        rows.append({"label": str(p["name"])[:80], "value": f"{p['value']} {unit}".strip()[:160],
                                     "where": f"{where} (product data)"})
                img = it.get("image")
                if img:
                    product["image"] = img[0] if isinstance(img, list) else (img.get("url") if isinstance(img, dict) else img)
    return rows, {k: v for k, v in product.items() if v}


def _web_text(soup):
    for tag in soup(["script", "style", "noscript", "svg", "nav", "footer", "header", "form", "iframe"]):
        tag.decompose()
    lines, seen = [], set()
    for line in soup.get_text("\n").split("\n"):
        line = re.sub(r"\s+", " ", line).strip()
        if len(line) > 2 and line.lower() not in seen:
            seen.add(line.lower())
            lines.append(line)
    return "\n".join(lines)


def _jina(url):
    """Read a JavaScript-only or server-blocking page through a page-rendering service (r.jina.ai)."""
    r = requests.get(JINA + url, headers={"Accept": "text/plain", "X-Return-Format": "markdown"}, timeout=45)
    r.raise_for_status()
    return r.text[:200_000]


RELATED = re.compile(r"spec|technical|tech-data|datasheet|data-sheet|download|parts|spare|accessor|dimension|feature|"
                     r"manual|document|support|catalog|brochure|variant|model", re.I)
SPEC_IMG = re.compile(r"spec|technical|datasheet|data-sheet|dimension|table|chart|rating|nameplate", re.I)


def _read_related(b, final, raw, pdf_links, max_pages=6, max_images=3):
    """Read the product's other pages on the same site (specs tab, downloads, spare parts, accessories) and its
    spec pictures (tables posted as images, read by Sarvam Vision)."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(raw.decode("utf-8", errors="ignore"), "html.parser")
    host = urlparse(final).netloc
    model_words = {w.lower() for w in re.findall(r"[A-Za-z]*\d[\w-]{2,}", b.get("title") or "")}
    cand, imgs = [], []
    for a in soup.find_all("a", href=True):
        href = urljoin(final, a["href"]).split("#")[0]
        u = urlparse(href)
        if u.scheme not in ("http", "https") or u.netloc != host or href.rstrip("/") == final.rstrip("/"):
            continue
        if re.search(r"login|signin|cart|checkout|account|privacy|cookie|career|contact|news|blog|\.(jpg|png|zip|exe)$", href, re.I):
            continue
        label = _cell(a)
        if href.lower().split("?")[0].endswith(".pdf"):
            continue
        hit = RELATED.search(label) or RELATED.search(u.path) or any(w in href.lower() for w in model_words)
        if hit and href not in cand:
            cand.append(href)
    for im in soup.find_all("img"):
        src = im.get("src") or im.get("data-src") or ""
        meta = " ".join([src, im.get("alt") or "", im.get("title") or ""])
        if src and SPEC_IMG.search(meta):
            full = urljoin(final, src)
            if full.startswith("http") and full not in imgs:
                imgs.append(full)

    def page(link):
        try:
            _, ct, data = _get(link, timeout=15)
            return link, ct, data
        except Exception:
            return link, "", b""
    read = []
    with ThreadPoolExecutor(max_workers=3) as ex:
        for link, ct, data in ex.map(page, cand[:max_pages]):
            if not data:
                continue
            if data[:4] == b"%PDF":
                pdf_links.append(link)
                continue
            s2 = BeautifulSoup(data.decode("utf-8", errors="ignore"), "html.parser")
            path = urlparse(link).path or link
            rows, _ = _web_structured(s2, f"web page {path[:60]}")
            text = _web_text(s2)
            if len(text) < 200 and not rows:
                continue
            src = len(b["sources"])
            b["sources"].append({"kind": "web", "ref": link, "note": "related page of the same product"})
            _add_page(b, src, 1, text[:30000], "web", kept=True)
            b["rows"] += rows
            _line_rows(b, b["pages"][-1], f"web page {path[:60]}")
            read.append(path[:50])
            for a in s2.find_all("a", href=True):
                h = urljoin(link, a["href"])
                if h.lower().split("?")[0].endswith(".pdf") and h not in pdf_links:
                    pdf_links.append(h)
    if read:
        b["notes"].append(f"Also read {len(read)} related page(s) of the same product: " + ", ".join(read))
    if imgs and ocr.available():
        done = 0
        for link in imgs[:max_images]:
            try:
                _, ct, data = _get(link, timeout=15)
                if not data or len(data) > 4_000_000:
                    continue
                md = ocr.image_text(data, ct or "image/jpeg")
            except Exception:
                md = None
            if md:
                src = len(b["sources"])
                b["sources"].append({"kind": "web", "ref": link, "note": "spec picture read by Sarvam Vision", "ocr_pages": [1]})
                _add_page(b, src, 1, md, "sarvam-ocr", kept=True)
                for t in ocr.md_tables(md):
                    _table_rows(b, t, "spec picture")
                _line_rows(b, b["pages"][-1], "spec picture")
                done += 1
        if done:
            b["notes"].append(f"Read {done} spec picture(s) on the page with Sarvam Vision.")


def read_url(url, follow_docs=True, pages_hint=None):
    from bs4 import BeautifulSoup
    b = new_bundle()
    url = check_url(url)
    try:
        final, ctype, raw = _get(url)
    except ValueError:
        raise
    except Exception as e:
        final, ctype, raw, err = url, "", b"", str(e)[:120]
    else:
        err = None
    if raw[:4] == b"%PDF" or "pdf" in ctype:
        return remember(_read_pdf_into(b, raw, final, pages_hint))
    src = len(b["sources"])
    b["sources"].append({"kind": "web", "ref": final, "note": ""})
    text, rows, product, links = "", [], {}, []
    if raw:
        soup = BeautifulSoup(raw.decode("utf-8", errors="ignore"), "html.parser")
        title = soup.find("meta", attrs={"property": "og:title"})
        b["title"] = (title.get("content") if title else (soup.title.string if soup.title else "")) or ""
        rows, product = _web_structured(soup, "web page table")
        og = soup.find("meta", attrs={"property": "og:image"})
        if og and og.get("content"):
            b["images"].append(urljoin(final, og["content"]))
        for a in soup.find_all("a", href=True):
            href, label = a["href"], _cell(a)
            if href.lower().split("?")[0].endswith(".pdf") or (DOC_LINK.search(label) and DOC_LINK.search(href)):
                full = urljoin(final, href)
                if full.startswith("http") and full not in links:
                    links.append(full)
        text = _web_text(soup)
    if len(text) < 500:  # JavaScript-only page, or the site blocked us
        try:
            text = _jina(final)
            b["sources"][src]["note"] = "read through a page-rendering service (the site needs JavaScript or blocks servers)"
            b["notes"].append("This site needed a page-rendering service to read.")
            for m in re.finditer(r"\[[^\]]*\]\((https?://[^)\s]+\.pdf)\)", text):
                if m.group(1) not in links:
                    links.append(m.group(1))
            md_rows = [ln for ln in text.split("\n") if ln.count("|") >= 2 and not set(ln.strip()) <= set("|-: ")]
            for ln in md_rows[:200]:
                cells = [c.strip() for c in ln.strip().strip("|").split("|")]
                if len(cells) >= 2 and cells[0] and any(cells[1:]):
                    rows.append({"label": cells[0][:80], "value": " | ".join(c for c in cells[1:] if c)[:200],
                                 "where": "web page table"})
        except Exception as e:
            if not text:
                raise ValueError(f"Couldn't open that page ({err or str(e)[:100]}). Some company sites block servers — "
                                 "upload the PDF manual or datasheet instead.")
    _add_page(b, src, 1, text[:60000], "web", kept=True)
    b["rows"] += rows
    _line_rows(b, b["pages"][-1], "web page")
    b["product"] = product
    if follow_docs and raw:
        _read_related(b, final, raw, links)
    if follow_docs and links:
        picked = sorted(links, key=lambda u: (not DOC_LINK.search(u), len(u)))[:4]
        for link in picked:
            try:
                _, ct, data = _get(link, timeout=30)
                if data[:4] == b"%PDF":
                    _read_pdf_into(b, data, link, None)
            except Exception:
                continue
        followed = [s["ref"] for s in b["sources"] if s["kind"] == "pdf"]
        if followed:
            b["notes"].append(f"Also read {len(followed)} linked document(s): " + ", ".join(u.rsplit('/', 1)[-1][:50] for u in followed))
    if not b["rows"] and not text:
        raise ValueError("That page has no readable text. Upload the PDF manual or datasheet instead.")
    tidy_rows(b)
    return remember(b)


# ---------- PDF ----------
def parse_pages_hint(hint, total):
    out = set()
    for part in re.split(r"[,\s]+", (hint or "").strip()):
        m = re.match(r"^(\d+)(?:-(\d+))?$", part)
        if m:
            a, z = int(m.group(1)), int(m.group(2) or m.group(1))
            out |= {p for p in range(min(a, z), max(a, z) + 1) if 1 <= p <= total}
    return sorted(out)[:30]


def _page_image_b64(plumber_pdf, n):
    from PIL import Image
    img = plumber_pdf.pages[n - 1].to_image(resolution=110).original.convert("RGB")
    if img.width > 1600:
        img = img.resize((1600, int(img.height * 1600 / img.width)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=80)
    return base64.b64encode(buf.getvalue()).decode()


VISION_PROMPT = ("This is one page of a machine's manual, datasheet or brochure (it may be a scan or a drawing). Copy what it "
                 "says EXACTLY, in its own language. Return ONLY JSON: {\"kind\": \"spec table|parts list|parts drawing|"
                 "text|drawing only\", \"rows\": [{\"label\": \"\", \"value\": \"\"}], \"text\": \"all other readable text as lines\"}. "
                 "Put every table row and every 'label: value' line in rows (for a parts list: label = part name, value = part "
                 "number and quantity). Keep numbers, units, model names and codes exactly as printed. Never guess unreadable text.")


def vision_page(b64, mime="image/jpeg"):
    data = llm.vision_json(VISION_PROMPT, b64, mime, max_tokens=1800)
    if not isinstance(data, dict):
        return None
    rows = [r for r in (data.get("rows") or []) if isinstance(r, dict) and r.get("label") and r.get("value")]
    return {"kind": data.get("kind") or "", "rows": rows, "text": str(data.get("text") or "")}


def _read_pdf_into(b, data, ref, pages_hint):
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception:
                raise ValueError("This PDF is password-protected. Remove the password and upload it again.")
        texts = [(p.extract_text() or "") for p in reader.pages[:400]]
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"Couldn't read that PDF: {str(e)[:100]}")
    src = len(b["sources"])
    total = len(texts)
    if not b["title"]:
        first = next((ln.strip() for ln in (texts[0] if texts else "").split("\n") if len(ln.strip()) > 3), "")
        b["title"] = first[:80]
    info = {"kind": "pdf", "ref": ref, "total_pages": total, "note": ""}
    b["sources"].append(info)
    for i, t in enumerate(texts):
        _add_page(b, src, i + 1, t, "text")
    mine = [p for p in b["pages"] if p["src"] == src]
    text_pages = [p for p in mine if len(p["text"]) >= 40]
    hint = parse_pages_hint(pages_hint, total)
    scanned = total and (sum(len(p["text"]) for p in mine) < 1500 or len(text_pages) / total < 0.15)
    # silver layer: pick the useful pages
    select(mine, hint)
    # pages to read with the vision AI: picture-only pages the person asked for, or the first pages of a scanned PDF
    cap = ocr.MAX_PAGES if ocr.available() else VISION_PAGES
    want = [n for n in hint if len(mine[n - 1]["text"]) < 40]
    if scanned and not want:
        want = list(range(1, min(total, cap) + 1))
    want = want[:cap]
    if want and ocr.available():  # Sarvam Vision first: proper OCR, Indian scripts, tables, handwriting
        has_text = any(len(p["text"]) >= 40 for p in mine)
        lang_hint = None if (not has_text or any(INDIC_CHARS.search(p["text"]) for p in mine[:20])) else "en-IN"
        got = ocr.pdf_pages(data, want, lang_hint) or {}
        for n, md in got.items():
            mine[n - 1].update(text=md, via="sarvam-ocr", kept=True, kind="ocr")
            for t in ocr.md_tables(md):
                _table_rows(b, t, f"{_short(ref)} page {n} (Sarvam Vision)")
        if got:
            info["ocr_pages"] = sorted(got)
            b["notes"].append(f"Read {len(got)} picture page(s) with Sarvam Vision: " + ", ".join(map(str, sorted(got))))
        elif ocr.last_error:
            b["notes"].append("Sarvam Vision couldn't read the picture pages, so the backup reader was used.")
        want = [n for n in want if n not in got][:VISION_PAGES]
    for p in mine:
        if p["kept"]:
            _line_rows(b, p, f"{_short(ref)} page {p['n']}")
    tables_from = sorted([p for p in mine if p["kept"] and len(p["text"]) >= 40], key=lambda p: -p.get("score", 0))[:8]
    tables_from = sorted(p["n"] for p in tables_from)
    if want or tables_from:
        try:
            import pdfplumber
            with pdfplumber.open(io.BytesIO(data)) as pdf:
                for n in tables_from:  # real tables on the useful pages
                    try:
                        for t in pdf.pages[n - 1].extract_tables()[:6]:
                            _table_rows(b, t, f"{_short(ref)} page {n}")
                    except Exception:
                        continue
                if want and llm.groq_available():  # backup: Groq's vision AI
                    imgs = {}
                    for n in want:
                        try:
                            imgs[n] = _page_image_b64(pdf, n)
                        except Exception:
                            continue
                    with ThreadPoolExecutor(max_workers=3) as ex:
                        results = dict(zip(imgs, ex.map(vision_page, imgs.values())))
                    read_ok = []
                    for n, res in results.items():
                        if not res:
                            continue
                        read_ok.append(n)
                        page = mine[n - 1]
                        page.update(text=(res["text"] + "\n" + "\n".join(f"{r['label']}: {r['value']}" for r in res["rows"])).strip(),
                                    via="vision", kept=True, kind=res["kind"])
                        for r in res["rows"]:
                            b["rows"].append({"label": str(r["label"])[:80], "value": str(r["value"])[:200],
                                              "where": f"{_short(ref)} page {n} (read from the page image)"})
                    if read_ok:
                        info["vision_pages"] = read_ok
                        b["notes"].append(f"Read {len(read_ok)} picture-only page(s) with the vision AI: "
                                          + ", ".join(str(n) for n in read_ok))
                elif want:
                    info["note"] = "picture-only pages need the Groq key to be read"
        except ImportError:
            info["note"] = "install pdfplumber for tables and scanned pages"
    kept = [p["n"] for p in mine if p["kept"]]
    if scanned and not info.get("vision_pages") and not info.get("ocr_pages"):
        b["notes"].append("This PDF is mostly pictures (a scan). " + (
            "Add the Sarvam or Groq key so it can be read." if not (llm.groq_available() or ocr.available()) else
            "The vision AI couldn't read it — try the page numbers with the specs."))
    b["notes"].append(f"{_short(ref)}: {total} page(s); used {len(kept)} useful page(s)"
                      + (f" ({', '.join(map(str, kept[:12]))}{'…' if len(kept) > 12 else ''})" if kept else "")
                      + (f"; {total - len(text_pages)} picture-only page(s)" if total - len(text_pages) else ""))
    info["kept_pages"] = kept
    tidy_rows(b)
    return b


def tidy_rows(b):
    """Table rows before plain-text lines (tables are more reliable), duplicates removed."""
    seen, out = set(), []
    for r in sorted(b["rows"], key=lambda r: r["where"].endswith(" text")):
        key = (re.sub(r"\W+", "", r["label"].lower()), re.sub(r"\W+", "", r["value"].lower())[:12])
        if key not in seen:
            seen.add(key)
            out.append(r)
    b["rows"] = out[:400]


PART_HEAD = re.compile(r"code|part ?no|part ?#|part number|item no|art\.? ?nr|ersatzteil", re.I)
NAME_HEAD = re.compile(r"description|name|part|item|bezeichnung", re.I)


def _table_rows(b, table, where):
    """Turn one table into exact rows. A header row becomes field names ('POWER: 53,000 BTU'); a parts list
    (description + code columns) becomes part name -> part number."""
    rows = [[re.sub(r"\s+", " ", c or "").strip() for c in r] for r in table if r]
    rows = [r for r in rows if any(r)]
    if not rows:
        return
    head = rows[0] if len(rows) > 1 and not any(re.search(r"\d{2,}", c) for c in rows[0]) and sum(1 for c in rows[0] if c) >= 2 else None
    if head and any(PART_HEAD.search(h) for h in head) and any(NAME_HEAD.search(h) for h in head):
        ci = next(i for i, h in enumerate(head) if PART_HEAD.search(h))
        ni = next((i for i, h in enumerate(head) if NAME_HEAD.search(h) and i != ci and not re.search(r"model", h, re.I)), None)
        last = ""
        for r in rows[1:80]:
            name = (r[ni] if ni is not None and ni < len(r) else "") or last
            last = name or last
            code = r[ci] if ci < len(r) else ""
            if name and code:
                extra = "; ".join(f"{h}: {v}" for h, v in zip(head, r) if v and h and h not in (head[ci], head[ni] if ni is not None else ""))
                b.setdefault("parts", []).append({"name": name[:60], "part_no": code[:40], "info": extra[:120], "where": f"{where} parts list"})
                b["rows"].append({"label": name[:80], "value": f"part no. {code}" + (f" ({extra})" if extra else ""),
                                  "where": f"{where} parts list"})
        return
    for r in (rows[1:] if head else rows)[:60]:
        cells = [c for c in r if c]
        if len(cells) < 2:
            continue
        if head and len(r) == len(head) and len(head) == 2:
            label, value = r[0] or cells[0], r[1] or cells[-1]  # simple 'item | value' table
        elif head and len(r) == len(head):
            label = r[0] or cells[0]
            value = "; ".join(f"{h}: {v}" for h, v in zip(head[1:], r[1:]) if v)
        else:
            label, value = cells[0], " | ".join(cells[1:])
        if label and value and len(label) < 80:
            b["rows"].append({"label": label[:80], "value": value[:240], "where": f"{where} table"})


LINE_ROW = re.compile(r"^([A-Za-z][A-Za-z ()/.#&,'-]{2,45}?)\s*[:=]?\s+(-?\d[\d.,]*(?:\s*(?:to|-|–|~|/)\s*-?\d[\d.,]*)?\s*"
                      r"(?:[A-Za-z%°/²³(\"”][A-Za-z0-9%°/²³().\"”]{0,13}(?:\s?[A-Za-z/²³]{1,6})?)?)\s*$")
JUNK_LABEL = re.compile(r"www\.|https?:|\.com\b|^(arial|helvetica|times|font|rev(ised)?|page|fig|figure|table|note|step|chapter|section|is set to)\b", re.I)


def _line_rows(b, page, where):
    """Spec lines written as plain text, e.g. 'Supply Voltage 380 VAC' or 'Capacity 22 KVA'."""
    for line in page["text"].split("\n")[:400]:
        m = LINE_ROW.match(line.strip())
        if m and not JUNK_LABEL.search(m.group(1)) and not m.group(1).strip().endswith(("(", "(Fig.")):
            b["rows"].append({"label": m.group(1).strip()[:60], "value": m.group(2).strip()[:60], "where": f"{where} text"})


def select(pages, hint=None, budget=BUDGET * 2):
    """Silver layer: keep the first two pages, any page the person asked for, then the most useful pages
    (spec / technical data first, then alarm & troubleshooting lists, parts lists, warranty, maintenance)."""
    def score(p):
        t = p["text"]
        bonus = 0
        for i, pat in enumerate([r"specification|technical data|technische daten|data sheet|datasheet|rated|power requirement",
                                 r"alarm list|troubleshoot|trouble shoot|error code", r"parts? list|parts diagram|spare parts",
                                 r"warranty", r"maintenance schedule|daily maintenance|lubrication"]):
            if re.search(pat, t, re.I):
                bonus = max(bonus, 50 - i * 5)
        return len(USEFUL.findall(t)) / (1 + len(t) / 3000) + bonus
    for p in pages:
        p["kept"] = False
        p["score"] = round(score(p), 1) if p["text"] else 0
    if not pages:
        return
    if sum(len(p["text"]) for p in pages) <= budget:
        for p in pages:
            p["kept"] = bool(p["text"])
        return
    size = 0
    for p in pages[:2] + [p for p in pages if p["n"] in (hint or [])]:
        if p["text"] and not p["kept"]:
            p["kept"] = True
            size += min(len(p["text"]), 2200)
    for p in sorted(pages, key=lambda p: -score(p)):
        if size > budget:
            break
        if p["text"] and not p["kept"] and (len(USEFUL.findall(p["text"])) >= 2 or MUST.search(p["text"])):
            p["kept"] = True
            size += min(len(p["text"]), 2200)


def read_pdf(data, name, pages_hint=None):
    if data[:4] != b"%PDF":
        raise ValueError("That file isn't a PDF")
    return remember(_read_pdf_into(new_bundle(), data, name, pages_hint))


def read_photo(b64, mime, name="photo"):
    if ocr.available():  # Sarvam Vision reads the exact text on the plate; the AI then understands it like any document
        md = ocr.image_text(base64.b64decode(b64), mime)
        if md:
            b = new_bundle(name)
            b["sources"].append({"kind": "photo", "ref": name, "note": "", "ocr_pages": [1]})
            _add_page(b, 0, 1, md, "sarvam-ocr", kept=True)
            for t in ocr.md_tables(md):
                _table_rows(b, t, "photo (Sarvam Vision)")
            _line_rows(b, b["pages"][0], "photo")
            for m in re.finditer(r"^\W*([A-Za-z][A-Za-z ()/.#-]{1,40}?)\s*[:=]\s*([^\n|]{1,80})$", md, re.M):
                b["rows"].append({"label": m.group(1).strip(), "value": m.group(2).strip(), "where": "photo"})
            b["notes"].append("Read the photo with Sarvam Vision.")
            tidy_rows(b)
            return remember(b)
    if not llm.groq_available():
        raise ValueError("Reading photos needs the Sarvam or Groq key")
    res = vision_page(b64, mime)
    if not res:
        raise ValueError(f"Couldn't read the photo: {llm.last_error}")
    b = new_bundle(name)
    b["sources"].append({"kind": "photo", "ref": name, "note": ""})
    _add_page(b, 0, 1, (res["text"] + "\n" + "\n".join(f"{r['label']}: {r['value']}" for r in res["rows"])).strip(),
              "vision", kept=True)
    b["rows"] = [{"label": str(r["label"])[:80], "value": str(r["value"])[:200], "where": "photo"} for r in res["rows"]]
    b["notes"].append("Read the photo with the vision AI.")
    return remember(b)


def read_text(text):
    b = new_bundle("Typed in")
    b["sources"].append({"kind": "text", "ref": "Typed in by the team", "note": ""})
    _add_page(b, 0, 1, text, "text", kept=True)
    for m in re.finditer(r"^([A-Za-z][A-Za-z ()/.-]{2,40})\s*[:=]\s*([^\n]{1,80})$", text or "", re.M):
        b["rows"].append({"label": m.group(1).strip(), "value": m.group(2).strip(), "where": "typed text"})
    return remember(b)


# ---------- what the AI gets ----------
def _short(ref):
    s = str(ref or "")
    return (s.rsplit("/", 1)[-1] or s)[:60]


def where_of(b, page):
    src = b["sources"][page["src"]]
    return "web page" if src["kind"] == "web" else ("photo" if src["kind"] == "photo" else f"{_short(src['ref'])} page {page['n']}")


def context(b, budget=BUDGET, rows_budget=4000):
    """Exact table rows first (they are the most reliable), then the useful pages with their page numbers."""
    parts, size = [], 0
    if b["product"]:
        parts.append("PRODUCT DATA (from the page's hidden structured data): " + json.dumps(b["product"], ensure_ascii=False)[:800])
    seen = set()
    rows = []
    for r in b["rows"]:
        key = (r["label"].lower(), r["value"].lower())
        if key not in seen:
            seen.add(key)
            rows.append(f"- {r['label']}: {r['value']}  [{r['where']}]")
    if rows:
        block = "\n".join(rows)[:rows_budget]
        parts.append("EXACT TABLE ROWS (copied from tables, most reliable):\n" + block)
        size += len(block)
    kept = [p for p in b["pages"] if p.get("kept") and p["text"]]
    kept.sort(key=lambda p: (p["n"] > 2, -p.get("score", 0)))
    for p in kept:
        if size > budget:
            break
        chunk = p["text"][:max(600, min(2200, budget - size))]
        parts.append(f"[{where_of(b, p)}]\n{chunk}")
        size += len(chunk)
    return "\n\n".join(parts)


def all_text(b):
    return "\n".join([json.dumps(b["product"], ensure_ascii=False)] + [f"{r['label']}: {r['value']}" for r in b["rows"]]
                     + [p["text"] for p in b["pages"]])


def summary(b):
    return {"id": b["id"], "title": b["title"], "notes": b["notes"], "parts": len(b.get("parts") or []),
            "sources": [{k: v for k, v in s.items() if k in ("kind", "ref", "total_pages", "kept_pages", "vision_pages", "ocr_pages", "note")}
                        for s in b["sources"]],
            "rows_found": len(b["rows"]), "image": (b["images"] or [None])[0] or b["product"].get("image")}
