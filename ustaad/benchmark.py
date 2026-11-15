"""
Reader accuracy: real maker documents with answer keys we checked by hand. The reader fills the form for each one,
then every expected value is compared after unit conversion, so "64 cfm" and "1812 l/min" count as the same answer.

Web cases run in the background (one every ~20 s, so Groq's free per-minute limit isn't hit). File cases run when
someone uploads the exact same file: it is matched by its SHA-256 fingerprint, so a different file is never scored
against the wrong answer key.
"""
import hashlib
import threading
import time
from datetime import datetime

from . import llm, machines, specs, store

CASES = [
    {"id": "kaeser-web", "title": "Kaeser workshop compressors (web page, a range of models)", "kind": "url", "industry": "factory",
     "source": "https://www.kaeser.com/in-en/products/reciprocating-compressors/stationary-reciprocating-compressors/oil-lubricated-workshop-compressors",
     "expect": [{"type": "compressor"},
                {"key": "pressure", "any": [10, 15], "why": "max pressure 10 or 15 bar"},
                {"key": "fad", "any": [112, 1050], "why": "displacement 112–1050 l/min"}]},
    {"id": "elgi-en11-sheet", "title": "ELGi EN 11 spec sheet (PDF link, 4 models; we pick EN 11-100)", "kind": "url", "industry": "factory",
     "source": "https://www.iacserv.com/content/IAC_PDF_Files/Spec_Sheet/ELGI_EN11_Spec_Sheet.pdf", "model": "EN 11-100",
     "expect": [{"type": "compressor"}, {"models_min": 3, "why": "EN 11-100 / 125 / 150 / 175"},
                {"key": "fad", "approx": 1812, "tol": 0.06, "why": "64 cfm = 1.81 m³/min"},
                {"key": "pressure", "approx": 6.89, "tol": 0.06, "why": "100 psi"},
                {"key": "motor_power", "approx": 11.19, "tol": 0.04, "why": "15 hp = 11.19 kW"},
                {"key": "noise", "approx": 67, "tol": 0.02, "why": "67 dB(A)"},
                {"key": "weight", "approx": 279.9, "tol": 0.04, "why": "617 lbs"}]},
    {"id": "bcas-en11-7v", "title": "ELGi EN 11-7 V performance sheet (PDF link)", "kind": "url", "industry": "factory",
     "source": "https://performance.bcas.org.uk/wp-content/uploads/2026/02/ELGi-EN-11-7-V-7barg-Variable.pdf", "model": "EN 11-7 V",
     "expect": [{"type": "compressor"},
                {"key": "pressure", "approx": 7.0, "tol": 0.03, "why": "7.0 bar g"},
                {"key": "fad", "approx": 1760, "tol": 0.04, "why": "1.76 m³/min"},
                {"key": "motor_power", "approx": 11.0, "tol": 0.03, "why": "11 kW"}]},
    {"id": "cpg-fryer-link", "title": "CPG gas fryer manual (PDF link, 4 models; we pick 351FCPG30N)", "kind": "url", "industry": "restaurant",
     "source": "https://cdnimg.webstaurantstore.com/documents/pdf/cpgfryers_manual.pdf", "model": "351FCPG30N",
     "expect": "fryer"},
    {"id": "cpg-fryer-file", "title": "CPG gas fryer manual (uploaded PDF)", "kind": "file", "industry": "restaurant",
     "sha256": "f412bb5e3f5b612e", "model": "351FCPG30N", "expect": "fryer"},
    {"id": "vmc1050-file", "title": "VMC 1050 machining centre manual (uploaded PDF, 211 pages, mostly scans)", "kind": "file",
     "industry": "factory", "sha256": "f1df6e0f54019dce",
     "expect": [{"type": "cnc"}, {"key": "voltage", "approx": 380, "tol": 0.01, "why": "380 VAC"},
                {"key": "frequency", "approx": 50, "tol": 0.01, "why": "50 Hz"},
                {"key": "power_capacity", "approx": 22, "tol": 0.01, "why": "22 KVA"},
                {"key": "air_pressure", "any": [4.9, 5.88], "why": "5–6 kgf/cm² = 4.9–5.9 bar"},
                {"key": "air_consumption", "approx": 500, "tol": 0.02, "why": "500 nl/min"}]},
]
FRYER = [{"type": "fryer"}, {"models_min": 4, "why": "351FCPG15L / 15N / 30L / 30N"},
         {"key": "heat_input", "approx": 15.53, "tol": 0.03, "why": "53,000 BTU = 15.5 kW"},
         {"key": "burners", "approx": 4, "tol": 0.01, "why": "4 burners"},
         {"key": "dimensions", "contains": "17", "why": "17” x 29” x 26.8”"},
         {"part": "01.02.1005190", "why": "fry basket part number"}, {"warranty_months": 12, "why": "1 year warranty"}]
for _c in CASES:
    if _c["expect"] == "fryer":
        _c["expect"] = FRYER

state = {"running": False, "current": None, "started": None}
_lock = threading.Lock()


def _nums(f):
    std = f.get("std")
    if isinstance(std, list):
        return [x for x in std if isinstance(x, (int, float))]
    return [std] if isinstance(std, (int, float)) else []


def score(case, draft):
    """Compare one filled form with the answer key."""
    fields = {f["key"]: f for f in draft.get("spec_fields") or []}
    checks = []
    for e in case["expect"]:
        if "type" in e:
            got, ok = draft.get("template"), draft.get("template") == e["type"]
            what, want = "machine type", e["type"]
        elif "models_min" in e:
            got = len(draft.get("models") or [])
            ok, what, want = got >= e["models_min"], "models found", f"≥ {e['models_min']}"
        elif "part" in e:
            parts = [p.get("part_no", "") for p in draft.get("parts_found") or []] + \
                    [c.get("part_no", "") for c in draft.get("components") or []]
            ok = any(e["part"] in (p or "") for p in parts)
            got, what, want = (e["part"] if ok else f"{len(parts)} part no(s), not this one"), "part number", e["part"]
        elif "warranty_months" in e:
            got = draft.get("warranty_months")
            ok, what, want = got == e["warranty_months"], "warranty (months)", e["warranty_months"]
        else:
            f = fields.get(e["key"]) or {}
            what = f.get("label") or e["key"]
            got = specs.show(f) if f.get("value") else ""
            if "contains" in e:
                ok, want = e["contains"] in str(f.get("value") or ""), f"contains {e['contains']}"
            elif "any" in e:
                ok = any(abs(n - w) <= 0.03 * w for n in _nums(f) for w in e["any"])
                want = " or ".join(f"{w:g}" for w in e["any"]) + f" {f.get('unit', '')}"
            else:
                ok = any(abs(n - e["approx"]) <= e.get("tol", 0.03) * e["approx"] for n in _nums(f))
                want = f"{e['approx']:g} {f.get('unit', '')}".strip()
            if ok and f.get("status") not in ("verified", "converted"):
                got = f"{got} (right, but not found word-for-word)"
        checks.append({"what": what, "want": str(want), "got": str(got or "—")[:80], "ok": bool(ok), "why": e.get("why", "")})
    passed = sum(c["ok"] for c in checks)
    return {"passed": passed, "total": len(checks), "pct": round(100 * passed / len(checks)) if checks else 0, "checks": checks}


def run_case(case, file_bytes=None):
    t = time.time()
    out = {"id": case["id"], "title": case["title"], "kind": case["kind"], "source": case.get("source", "uploaded file"),
           "when": datetime.now().isoformat(timespec="seconds"), "ai": llm.available()}
    try:
        if case["kind"] == "file":
            draft = machines.read_source(case["industry"], file=(file_bytes, case["id"] + ".pdf", "application/pdf"), model=case.get("model"))
        else:
            draft = machines.read_source(case["industry"], url=case["source"], model=case.get("model"))
        out.update(score(case, draft))
        out["notes"] = (draft.get("read") or {}).get("notes", [])[:3]
    except Exception as e:  # a site that blocks us, a timeout, an AI hiccup — reported, never hidden
        out.update({"passed": 0, "total": len(case["expect"]), "pct": 0, "checks": [], "error": str(e)[:200]})
    out["seconds"] = round(time.time() - t, 1)
    return out


def results():
    try:
        r = store.meta_get("bench:last")
        return r if isinstance(r, dict) else {}
    except Exception:
        return {}


def _save(res):
    with _lock:
        cur = results()
        cur[res["id"]] = res
        store.meta_set("bench:last", cur)


def overview():
    last = results()
    rows = [{**{k: c[k] for k in ("id", "title", "kind")}, "source": c.get("source", ""), "checks": len(c["expect"]),
             "last": last.get(c["id"])} for c in CASES]
    done = [r["last"] for r in rows if r["last"] and r["last"].get("total")]
    passed, total = sum(r["passed"] for r in done), sum(r["total"] for r in done)
    return {"cases": rows, "running": state["running"], "current": state["current"],
            "overall": {"passed": passed, "total": total, "pct": round(100 * passed / total) if total else None,
                        "cases_run": len(done)}, "ai": llm.available()}


def run_web(only=None, gap=20):
    """Run the web cases one after another in the background."""
    if state["running"]:
        return False
    todo = [c for c in CASES if c["kind"] == "url" and (not only or c["id"] == only)]
    if not todo:
        raise ValueError("Unknown test")

    def go():
        state.update(running=True, started=datetime.now().isoformat(timespec="seconds"))
        try:
            for i, c in enumerate(todo):
                state["current"] = c["id"]
                _save(run_case(c))
                if i < len(todo) - 1 and llm.available():
                    time.sleep(gap)
        finally:
            state.update(running=False, current=None)
    threading.Thread(target=go, daemon=True).start()
    return True


def run_file(data):
    digest = hashlib.sha256(data).hexdigest()
    case = next((c for c in CASES if c["kind"] == "file" and digest.startswith(c["sha256"])), None)
    if not case:
        return {"matched": False, "fingerprint": digest[:16],
                "message": "This file has no answer key, so it can't be scored. Use ＋ Add to read it — the colours still show what was checked."}
    res = run_case(case, data)
    _save(res)
    return {"matched": True, **res}
