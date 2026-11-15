"""
The expert read: Ustaad reads a machine's manual the way a senior engineer of that field would, and builds
  1. a MACHINE REPORT — what it is, its working window, what will break first and why, a full maintenance plan,
     critical spares, safety, and what the manual doesn't say;
  2. a UNIVERSAL PROFILE — one standard for every machine (layers modelled on ISO 14224, the international standard
     for maintenance data): identity, core ratings, type-specific specs, part tree, links;
  3. a PART TREE — machine -> assemblies -> parts, each part with its own details.

Honesty rules: every conclusion carries its page. If its quote is really on that page it is "📘 Manual says";
a conclusion without a checkable quote is "🧠 Expert conclusion". Code checks the quotes, not the AI.

Big manuals are read section by section in the background; Groq and Sarvam read different sections at the same time.
"""
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from . import llm, packs, specs, store

EXPERTS = {
    "cnc": "a senior CNC machine service engineer with 20 years in Indian machine shops",
    "lathe": "a senior lathe and turning-centre service engineer",
    "compressor": "a senior air-compressor service engineer who has rebuilt hundreds of screw and piston compressors",
    "press": "a senior hydraulic and power-press maintenance engineer",
    "boiler": "a senior boiler inspector and steam-plant maintenance engineer",
    "generator": "a senior diesel-generator (DG set) service engineer",
    "pump": "a senior pump reliability engineer",
    "fryer": "a senior commercial-kitchen equipment technician who services gas and electric fryers",
    "cold": "a senior refrigeration and cold-room technician",
    "oven": "a senior commercial-kitchen technician for ovens, tandoors and griddles",
    "ventilator": "a senior biomedical engineer who services ICU ventilators",
    "infusion-pump": "a senior biomedical engineer who services infusion pumps",
    "autoclave": "a senior biomedical engineer who services autoclaves and sterilisers",
    "vehicle": "a senior automobile service advisor and master technician",
    "software": "a senior site-reliability engineer",
    "general": "a senior maintenance engineer with 20 years of experience",
}

# the universal profile — the same layers for every machine
IDENTITY = [("maker", "Maker"), ("model", "Model"), ("variant", "Variant / version"), ("serial_no", "Serial number"),
            ("year", "Year made"), ("country", "Made in"), ("certification", "Certifications (CE, BIS, ISI…)"),
            ("site", "Location"), ("vendor", "Vendor / service partner"), ("warranty", "Warranty"),
            ("install_date", "Installed on")]
CORE = [("power", "Power"), ("voltage", "Supply voltage"), ("phase", "Phase"), ("frequency", "Frequency"),
        ("current", "Rated current"), ("dimensions", "Size (L × W × H)"), ("weight", "Weight"), ("noise", "Noise"),
        ("operating_temp", "Working temperature"), ("ip_rating", "IP / protection rating"),
        ("consumables", "Consumables (oil, coolant, gas, air, water)"), ("capacity", "Main capacity"),
        ("duty_cycle", "Duty cycle"), ("controller", "Controller / software")]
# spec-template fields that already answer a universal one
FROM_SPECS = {"voltage": ["voltage"], "frequency": ["frequency"], "weight": ["weight"], "noise": ["noise"],
              "dimensions": ["dimensions", "table_size"], "power": ["motor_power", "spindle_power", "heat_input", "power_capacity",
                                                                   "rated_power", "power"],
              "controller": ["controller"], "capacity": ["fad", "oil_capacity", "capacity", "spindle_speed", "tonnage"]}

CHUNK = 5500
MAX_SECTIONS = 10
progress = {}  # (industry, asset_id) -> {"state", "done", "total", "started", "error"}
_lock = threading.Lock()


def _norm(t):
    return re.sub(r"[^a-z0-9]+", " ", (t or "").lower()).strip()


def _quote_on_page(quote, page_text):
    """True if the quote (or a long-enough piece of it) is really on that page."""
    q, t = _norm(quote), _norm(page_text)
    if len(q) < 6 or not t:
        return False
    if q in t:
        return True
    words = q.split()
    if len(words) >= 5:  # allow small OCR / spacing differences: 5 words in a row must match
        return any(" ".join(words[i:i + 5]) in t for i in range(len(words) - 4))
    return False


def _sections(pages):
    """Useful pages first (kept / read by OCR), cut into sections of ~5,500 characters."""
    use = [p for p in pages if p.get("kept")] or pages
    use = sorted(use, key=lambda p: (p["source"], p["page"]))
    out, cur, size = [], [], 0
    for p in use:
        t = p["text"][:CHUNK]
        if size + len(t) > CHUNK and cur:
            out.append(cur)
            cur, size = [], 0
        cur.append({**p, "text": t})
        size += len(t)
    if cur:
        out.append(cur)
    return out[:MAX_SECTIONS]


MAP_PROMPT = ('You are {who}. You are reading part of the maker\'s manual for {name} ({maker} {model}). Read it like an expert '
              'and pull out everything a maintenance team must know. Use ONLY these pages. For every item give the page number '
              'and an EXACT short quote (5-20 words copied from the page). Return ONLY JSON: '
              '{{"facts": [{{"kind": "purpose|limit|failure|maintenance|safety|consumable|spec|other", "text": "plain English", '
              '"page": 0, "quote": ""}}], '
              '"parts": [{{"assembly": "e.g. Spindle unit", "name": "", "part_no": "", "qty": "", "spec": "e.g. bearing 7014 C", '
              '"interval": "e.g. replace every 2000 h", "failure_signs": "", "alarm_codes": [""], "page": 0, "quote": ""}}], '
              '"identity": {{"serial_no|year|country|certification|variant": {{"value": "", "page": 0, "quote": ""}}}}, '
              '"core": {{"power|voltage|phase|frequency|current|dimensions|weight|noise|operating_temp|ip_rating|consumables|'
              'capacity|duty_cycle|controller": {{"value": "with unit", "page": 0, "quote": ""}}}}}}. '
              'Leave out anything not on these pages. Keep codes and numbers exact.')

REDUCE_PROMPT = ('You are {who}. Below are notes an assistant took while reading the whole manual of {name} ({maker} {model}), '
                 'each with its page. Write the machine report a senior engineer would hand a new technician. Draw real '
                 'conclusions (what the limits mean in practice, which part will fail first and why, what to stock), but say '
                 'which ones come from the manual (give its page and quote) and which are your expert conclusions (basis: '
                 '"expert", with "because"). Return ONLY JSON: {{"summary": "3-4 sentences", "what_it_is": "", '
                 '"good_for": [""], "not_good_for": [""], '
                 '"operating_window": [{{"what": "", "range": "", "page": 0, "quote": ""}}], '
                 '"likely_failures": [{{"part": "", "why": "", "signs": "", "alarm_codes": [""], "basis": "manual|expert", '
                 '"because": "", "page": 0, "quote": ""}}], '
                 '"maintenance": {{"daily": [{{"task": "", "page": 0, "quote": ""}}], "weekly": [], "monthly": [], "yearly": []}}, '
                 '"critical_spares": [{{"name": "", "part_no": "", "why": ""}}], '
                 '"safety": [{{"text": "", "page": 0, "quote": ""}}], '
                 '"gaps": ["what the manual does not say and should be asked from the vendor"]}}. '
                 'At most 8 items per list. Plain, simple English. Never invent part numbers or values.')


def _who(a):
    return EXPERTS.get(a.get("template") or specs.guess_type(a.get("type", ""), a.get("type_key")), EXPERTS["general"])


def _map(a, section, first):
    pages = "\n\n".join(f"[page {p['page']}]\n{p['text']}" for p in section)
    data, by = llm.chat_json_via(first, MAP_PROMPT.format(who=_who(a), name=a.get("name", ""), maker=a.get("maker", ""),
                                                          model=a.get("model", "")), pages, 3000)
    return (data if isinstance(data, dict) else {}), by


def _check(item, page_text_of):
    """Mark an item 📘 (quote really on that page) or 🧠 (expert conclusion / quote not found)."""
    page, quote = item.get("page"), (item.get("quote") or "").strip()
    try:
        page = int(page) if page not in (None, "", 0, "0") else None
    except (TypeError, ValueError):
        page = None
    item["page"] = page
    if quote and page and _quote_on_page(quote, page_text_of(page)):
        item["basis"], item["checked"] = "manual", True       # 📘 the quote is really on that page
    elif quote and item.get("basis") != "expert":
        item["basis"], item["checked"] = "unchecked", False   # said to be from the manual, but the quote wasn't found
    else:
        item["basis"], item["checked"] = "expert", False      # 🧠 an expert conclusion
    return item


def build(industry, aid):
    """Read the stored manual pages and build report + universal profile + part tree. Runs in the background."""
    key = (industry, aid)
    a = packs.asset(industry, aid)
    pages = store.manual_pages(industry, aid)
    by_page = {}
    for p in pages:
        by_page.setdefault(p["page"], p["text"])
    page_text_of = lambda n: by_page.get(n, "")  # noqa: E731
    sections = _sections(pages) if pages else []
    progress[key] = {"state": "running", "done": 0, "total": len(sections), "started": time.time(), "error": None}
    notes, used = {"facts": [], "parts": [], "identity": {}, "core": {}}, set()
    try:
        if sections and llm.available():
            def work(i):
                data, by = _map(a, sections[i], "groq" if i % 2 == 0 else "sarvam")  # two brains, side by side
                with _lock:
                    progress[key]["done"] += 1
                if by:
                    used.add(by)
                return data
            with ThreadPoolExecutor(max_workers=2) as ex:
                for data in ex.map(work, range(len(sections))):
                    for k in ("facts", "parts"):
                        notes[k] += [x for x in data.get(k) or [] if isinstance(x, dict)]
                    for k in ("identity", "core"):
                        for f, v in (data.get(k) or {}).items():
                            if isinstance(v, dict) and v.get("value") and f not in notes[k]:
                                notes[k][f] = v
        report = _reduce(a, notes, page_text_of, used) if notes["facts"] and llm.available() else _rule_report(industry, a)
        universal = _universal(industry, a, notes, page_text_of)
        tree = _part_tree(a, notes["parts"], report, page_text_of)
        meta = {"built": datetime.now().isoformat(timespec="seconds"), "pages_read": sum(len(s) for s in sections),
                "sections": len(sections), "by": " + ".join(sorted(used)) or ("rules (no AI key)" if not llm.available() else "—"),
                "facts": len(notes["facts"])}
        _save(industry, aid, report=report, universal=universal, part_tree=tree, report_meta=meta)
        progress[key].update(state="done")
    except Exception as e:  # never leave it spinning
        progress[key].update(state="failed", error=str(e)[:200])
    return progress[key]


def _reduce(a, notes, page_text_of, used):
    facts = [_check(f, page_text_of) for f in notes["facts"][:160]]
    lines = "\n".join(f"- [{f.get('kind', 'other')}] {f.get('text', '')} (p.{f.get('page') or '?'}; quote: \"{(f.get('quote') or '')[:120]}\")"
                      for f in facts)[:14000]
    parts = "\n".join(f"- {p.get('assembly', '')} / {p.get('name', '')} {p.get('part_no', '')} {p.get('interval', '')} (p.{p.get('page') or '?'})"
                      for p in notes["parts"][:60])[:3000]
    data, by = llm.chat_json_via("groq", REDUCE_PROMPT.format(who=_who(a), name=a.get("name", ""), maker=a.get("maker", ""),
                                                              model=a.get("model", "")),
                                 f"NOTES:\n{lines}\n\nPARTS SEEN:\n{parts}", 3500)
    if by:
        used.add(by)
    if not isinstance(data, dict):
        return _rule_report(None, a, facts)
    for k in ("operating_window", "likely_failures", "safety"):
        data[k] = [_check(x, page_text_of) for x in (data.get(k) or []) if isinstance(x, dict)][:8]
    mt = data.get("maintenance") if isinstance(data.get("maintenance"), dict) else {}
    data["maintenance"] = {k: [_check(x if isinstance(x, dict) else {"task": str(x)}, page_text_of) for x in (mt.get(k) or [])][:10]
                           for k in ("daily", "weekly", "monthly", "yearly")}
    for k in ("good_for", "not_good_for", "gaps"):
        data[k] = [str(x) for x in (data.get(k) or []) if x][:8]
    data["critical_spares"] = [x for x in (data.get("critical_spares") or []) if isinstance(x, dict) and x.get("name")][:10]
    return data


def _rule_report(industry, a, facts=None):
    """No AI: a plain report from what is already known (manual items, specs, parts)."""
    items = store.manual_items(industry or "", a["id"]) if industry else []
    faults = [m for m in items if m["kind"] == "fault"]
    service = [m for m in items if m["kind"] == "service"]
    return {"summary": f"{a.get('name', a['id'])} ({a.get('maker', '')} {a.get('model', '')}).".strip(),
            "what_it_is": a.get("summary") or a.get("type", ""), "good_for": [], "not_good_for": [],
            "operating_window": [{"what": f["label"], "range": specs.show(f), "page": None, "basis": "manual", "checked": f.get("status") in ("verified", "converted")}
                                 for f in a.get("spec_fields") or [] if f.get("value")][:8],
            "likely_failures": [{"part": m["title"], "why": m["text"][:200], "signs": "", "basis": "manual", "checked": True, "page": None} for m in faults][:8],
            "maintenance": {"daily": [], "weekly": [], "monthly": [{"task": m["title"], "basis": "manual", "checked": True, "page": None} for m in service][:10], "yearly": []},
            "critical_spares": [{"name": c["name"], "part_no": c.get("part_no", ""), "why": "listed spare"} for c in a.get("components") or []][:10],
            "safety": [], "gaps": ["Add the Groq or Sarvam key for the full expert report."], "rule_based": True}


def _universal(industry, a, notes, page_text_of):
    pk = packs.get(industry)
    site = next((s["name"] for s in pk.get("sites", []) if s["id"] == a.get("site")), a.get("site", ""))
    known = {"maker": a.get("maker"), "model": a.get("model"), "site": site, "vendor": a.get("vendor"),
             "warranty": f"until {a['warranty_until']}" if a.get("warranty_until") else "", "install_date": a.get("install_date")}
    fields = {f["key"]: f for f in a.get("spec_fields") or [] if f.get("value")}
    out = {}
    for layer, defs in (("identity", IDENTITY), ("core", CORE)):
        for k, label in defs:
            v = {"label": label, "value": "", "source": "", "page": None, "checked": False}
            if known.get(k):
                v.update(value=str(known[k]), source="entered", checked=True)
            elif any(fields.get(x) for x in FROM_SPECS.get(k, [])):
                f = next(fields[x] for x in FROM_SPECS[k] if fields.get(x))
                v.update(value=specs.show(f), source=f.get("where", "spec sheet"), checked=f.get("status") in ("verified", "converted"))
            elif isinstance(notes[layer].get(k), dict):
                n = _check(dict(notes[layer][k]), page_text_of)
                v.update(value=str(n["value"])[:80], source="manual", page=n.get("page"), quote=n.get("quote", ""), checked=n["checked"])
            out.setdefault(layer, {})[k] = v
    return out


def _slug(t):
    return re.sub(r"[^a-z0-9]+", "-", (t or "").lower()).strip("-")[:40] or "part"


def _part_tree(a, parts, report, page_text_of):
    """Machine -> assemblies -> parts. Parts the team already tracks (stock, service days) are merged in."""
    merged, order = {}, []
    for p in parts:
        name = str(p.get("name") or "").strip()
        if not name:
            continue
        k = _norm(p.get("part_no") or "") or _norm(name)
        if k in merged:
            for f, v in p.items():
                if v and not merged[k].get(f):
                    merged[k][f] = v
            continue
        merged[k] = _check({**p, "name": name[:60]}, page_text_of)
        order.append(k)
    for c in a.get("components") or []:  # the team's own list (stock, service interval)
        k = _norm(c.get("part_no") or "") or _norm(c["name"])
        hit = merged.get(k) or next((merged[x] for x in order if _norm(merged[x]["name"]) == _norm(c["name"])), None)
        if hit:
            hit.update(stock=c.get("stock"), every_days=c.get("every_days"), tracked=True)
        else:
            merged[k] = {"name": c["name"], "part_no": c.get("part_no", ""), "assembly": "", "stock": c.get("stock"),
                         "every_days": c.get("every_days"), "tracked": True}
            order.append(k)
    critical = {_norm(x.get("part") or x.get("name") or "") for x in (report.get("likely_failures") or []) + (report.get("critical_spares") or [])}
    tree = {}
    for k in order:
        p = merged[k]
        p["id"] = _slug(p.get("part_no") or p["name"])
        p["alarm_codes"] = [str(x) for x in (p.get("alarm_codes") or []) if x][:6]
        consumable = re.search(r"filter|oil|grease|belt|seal|gasket|o-ring|fuse|lamp|basket|wiper", p["name"], re.I)
        p["criticality"] = ("A" if (_norm(p["name"]) in critical or p["alarm_codes"]) else "C" if consumable else "B")
        tree.setdefault((p.get("assembly") or "Other parts").strip()[:40] or "Other parts", []).append(p)
    return [{"assembly": k, "parts": v[:40]} for k, v in sorted(tree.items(), key=lambda kv: (kv[0] == "Other parts", kv[0]))][:20]


def completeness(universal, tree):
    vals = [v for layer in (universal or {}).values() for v in layer.values()]
    filled = sum(1 for v in vals if v.get("value"))
    parts = [p for g in tree or [] for p in g["parts"]]
    with_no = sum(1 for p in parts if p.get("part_no"))
    score = (0.8 * filled / len(vals) if vals else 0) + (0.2 * with_no / len(parts) if parts else 0)
    missing = [v["label"] for v in vals if not v.get("value")]
    return {"pct": round(100 * score), "filled": filled, "fields": len(vals), "parts": len(parts), "parts_with_no": with_no,
            "missing": missing, "parts_missing_no": [p["name"] for p in parts if not p.get("part_no")][:12]}


def vendor_message(industry, aid):
    a = packs.asset(industry, aid)
    data = view(industry, aid)
    c = data["completeness"]
    ident = ", ".join(x for x in [a.get("maker"), a.get("model")] if x)
    lines = [f"Hello{(' ' + a['vendor']) if a.get('vendor') else ''},",
             f"For our {a.get('name', aid)}{f' ({ident})' if ident else ''}, could you please share:"]
    lines += [f"- {m}" for m in c["missing"][:12]]
    if c["parts_missing_no"]:
        lines.append("- Part numbers for: " + ", ".join(c["parts_missing_no"]))
    lines.append("Thank you.")
    return "\n".join(lines)


def _save(industry, aid, **fields):
    a = dict(packs.asset(industry, aid) or {})
    a.update(fields)
    store.save_machine(industry, a, a.get("added_by") or "")


def start(industry, aid):
    """Begin (or restart) the expert read in the background."""
    if not packs.asset(industry, aid):
        raise ValueError("Unknown item")
    cur = progress.get((industry, aid))
    if cur and cur["state"] == "running" and time.time() - cur["started"] < 600:
        return cur
    progress[(industry, aid)] = {"state": "running", "done": 0, "total": 0, "started": time.time(), "error": None}
    threading.Thread(target=build, args=(industry, aid), daemon=True).start()
    return progress[(industry, aid)]


def view(industry, aid):
    a = packs.asset(industry, aid)
    if not a:
        raise ValueError("Unknown item")
    universal = a.get("universal") or _universal(industry, a, {"identity": {}, "core": {}}, lambda n: "")
    tree = a.get("part_tree") or _part_tree(a, [], {}, lambda n: "")
    return {"report": a.get("report"), "meta": a.get("report_meta"), "universal": universal, "part_tree": tree,
            "completeness": completeness(universal, tree), "progress": progress.get((industry, aid)),
            "manual_pages": len(store.manual_pages(industry, aid)), "expert": _who(a)}


def part(industry, aid, pid):
    """Everything about one part: details, manual page, service, stock, alarms, and the team's real fixes on it."""
    a = packs.asset(industry, aid)
    tree = view(industry, aid)["part_tree"]
    p = next((x for g in tree for x in g["parts"] if x["id"] == pid), None)
    if not p:
        raise ValueError("Unknown part")
    words = [w for w in _norm(p["name"]).split() if len(w) > 3] or _norm(p["name"]).split()
    recs = [r for r in store.records(industry) if r["asset_id"] == aid and r["status"] != "rejected"]
    hits = []
    for r in reversed(recs):
        blob = _norm(" ".join([r.get("problem", ""), r.get("cause", ""), r.get("action", ""), r.get("code") or ""]))
        if any(w in blob for w in words) or any(c and c in blob for c in p.get("alarm_codes") or []):
            hits.append({"date": r["datetime"][:10], "problem": r["problem"], "action": r["action"], "outcome": r["outcome"],
                         "person": (packs.person(industry, r["person_id"]) or {}).get("name", "")})
    from . import machines
    due = next((x for x in machines.service_due(industry, a) if _norm(x["what"]) == _norm(p["name"])), None)
    return {"part": p, "fixes": hits[:10], "service_due": due, "asset": {"id": aid, "name": a.get("name")}}
