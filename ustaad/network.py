"""
🌐 Plants learning from each other.

Every plant that opts in shares its fixes WITHOUT names: no people, no company, no exact place — only the machine
model/type, the problem, what was done and whether it worked. When you ask about CNC-3 (an HMC-500), Ustaad also shows
what worked for the same problem on HMC-500s in other plants.

In this demo the other plants are SAMPLE data (data/network.json), clearly labelled. In a real deployment they would be
one shared memory bank that every customer's opted-in fixes flow into.
"""
import json
import re
from datetime import date

from . import config, packs, store

_DATA = None
STOP = {"the", "and", "with", "after", "when", "not", "has", "had", "was", "are", "for", "from", "this", "that", "its", "too",
        "very", "again", "machine", "problem", "issue", "please", "what", "how", "why", "our", "any", "help", "check", "light",
        "high", "low", "fault", "error", "alarm", "code"}


def _data():
    global _DATA
    if _DATA is None:
        try:
            _DATA = json.loads((config.ROOT / "data" / "network.json").read_text(encoding="utf-8"))
        except Exception:
            _DATA = {}
    return _DATA


def _words(text):
    return {w[:5] for w in re.findall(r"[a-z]{3,}", (text or "").lower()) if w not in STOP}


def _codes(text):
    return {c.upper() for c in re.findall(r"\b([A-Z]?\d{2,5})\b", text or "", re.I)}


def word(industry):
    return (_data().get(industry) or {}).get("word", "sites")


def _matches(case, words, codes):
    if codes and case.get("code") and case["code"].upper() in codes:
        return True
    return len(words & _words(case["problem"])) >= 2 or (len(_words(case["problem"])) == 1 and words & _words(case["problem"]))


def lookup(industry, asset, problem):
    """What other plants did for this problem on the same model (or else the same type). None if too few cases."""
    cases = (_data().get(industry) or {}).get("cases") or []
    if not cases or not asset or asset.get("id") == "ANY":
        return None
    words, codes = _words(problem), _codes(problem)
    hits = [c for c in cases if _matches(c, words, codes)]
    same_model = [c for c in hits if c["model"] == asset.get("model")]
    use, match = (same_model, f"the same {asset.get('model')}") if same_model else \
        ([c for c in hits if c["type"] == asset.get("type")], f"the same kind of {(asset.get('type') or 'machine').lower()}")
    if len(use) < 3:
        return None
    groups = {}
    for c in use:
        g = groups.setdefault(c["fix"], {"fix": c["fix"], "cause": c["cause"], "worked": 0, "tried": 0, "minutes": []})
        g["tried"] += 1
        if c["outcome"] == "fixed":
            g["worked"] += 1
            g["minutes"].append(c["minutes"])
    fixes = []
    for g in groups.values():
        m = g.pop("minutes")
        fixes.append({**g, "rate": round(g["worked"] / g["tried"], 2), "avg_minutes": round(sum(m) / len(m)) if m else None})
    fixes.sort(key=lambda f: (-f["worked"], -f["rate"]))
    return {"word": word(industry), "plants": len({c["plant"] for c in use}), "cases": len(use), "match": match,
            "problem": use[0]["problem"], "fixes": fixes[:4], "sample": True,
            "note": f"From other {word(industry)} with {match}. Names, companies and places are never shared."}


# ---------- sharing our own fixes (opt-in, names removed) ----------
def settings(industry):
    s = store.meta_get(f"network:settings:{industry}") or {}
    return {"share": s.get("share", True), "shared": len((store.meta_get(f"network:shared:{industry}") or {}).get("cases") or []),
            "word": word(industry), "has_network": bool((_data().get(industry) or {}).get("cases"))}


def set_share(industry, on):
    store.meta_set(f"network:settings:{industry}", {"share": bool(on)})
    return settings(industry)


def _scrub(industry, text):
    """Remove people's names, the company and site names from a fix before it leaves the plant."""
    pk = packs.get(industry)
    out = text or ""
    swap = {}
    for p in pk.get("people") or []:
        for n in (p["name"], p["name"].split()[0], p.get("short", "")):
            swap[n] = "a technician"
    for n, word in [(pk["org"]["name"], "the company")] + [(x.get("name", ""), "[place]") for x in pk.get("sites") or []]:
        for part in [n, re.sub(r"\s*\(.*?\)", "", n)] + re.findall(r"\((.*?)\)", n):  # "Kaveri (demo)" -> also "Kaveri"
            if part.strip().lower() not in ("demo", ""):
                swap[part.strip()] = word
    for n in sorted((n for n in swap if n and len(n) > 2), key=len, reverse=True):  # longest first: "Ramesh-ji" before "Ramesh"
        out = re.sub(r"\b" + re.escape(n) + r"\b", swap[n], out, flags=re.I)
    return out


def share(industry, rec):
    """Called when a fix is logged: keep an anonymous copy for other plants (if this plant opted in)."""
    if not rec or not settings(industry)["share"] or rec.get("outcome") not in ("fixed", "failed_again", "temporary"):
        return None
    a = packs.asset(industry, rec.get("asset_id")) or {}
    if not a:
        return None
    key = f"network:shared:{industry}"
    cur = (store.meta_get(key) or {}).get("cases") or []
    if any(c.get("ref") == rec["id"] for c in cur):
        cur = [c for c in cur if c.get("ref") != rec["id"]]
    cur.append({"ref": rec["id"], "model": a.get("model"), "type": a.get("type"), "problem": rec.get("problem"),
                "code": rec.get("code") or "", "fix": _scrub(industry, rec.get("action")), "cause": _scrub(industry, rec.get("cause")),
                "outcome": rec.get("outcome"), "minutes": rec.get("downtime_minutes"), "year": date.today().year})
    store.meta_set(key, {"cases": cur[-500:]})
    return cur[-1]
