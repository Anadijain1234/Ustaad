"""
Smart diagnosis — maths on the team's own records (no AI needed, so every number can be explained):

  causes()        P(cause | this problem, this machine model) from past cases, smoothed so 2 cases don't look certain;
                  then the SMARTEST CHECK ORDER: highest chance per minute first (probability ÷ time), which gives the
                  shortest average time to find the real cause.
  aging()         a fix that worked long ago and was never re-confirmed, or failed since, loses trust.
  cost_incidents  repairs where a fix already in memory would have saved hours and money ("cost of not asking").
  patterns()      the pattern detective: repeats and their rhythm, what stopped a problem and for how long, shift clusters.
  maker_limits()  sensor limits from the maker's documents ("manual p.45: max 60 °C").
  stops / uptime  downtime reasons and uptime %; part_life() by running hours, not by calendar.
"""
import math
import re
import statistics
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

from . import packs, store

HALF_LIFE_DAYS = 540      # an unconfirmed memory counts half after ~18 months
PARTS = ["bearing", "coupling", "spider", "belt", "seal", "o-ring", "oring", "gasket", "switch", "valve", "sensor", "filter",
         "pump", "motor", "hose", "fuse", "relay", "thermostat", "thermocouple", "igniter", "pilot", "burner", "contactor",
         "encoder", "drive", "cable", "connector", "battery", "capacitor", "fan", "compressor", "solenoid", "regulator",
         "nozzle", "spring", "chain", "gear", "clamp", "joint", "lubrication", "lube", "coolant", "oil", "alignment",
         "software", "firmware", "certificate", "dns", "memory", "disk", "config", "network", "power", "wiring", "board"]
STOP_REASONS = {"breakdown": "Breakdown", "waiting_part": "Waiting for a part", "no_operator": "No operator",
                "setup": "Setup / changeover", "planned": "Planned maintenance", "power": "Power cut",
                "quality": "Quality check", "other": "Other"}


def _tok(t):
    from .memory import _tokens
    return set(_tokens(t or ""))


def _days_ago(dt):
    try:
        return max(0, (datetime.now() - datetime.fromisoformat(str(dt)[:19])).days)
    except Exception:
        return 0


def _recency(dt):
    return 0.5 ** (_days_ago(dt) / HALF_LIFE_DAYS)


def cause_key(text, extra_words=()):
    """Group differently-worded causes: 'Assumed front spindle bearing wear' and 'bearing failed again' -> 'bearing'."""
    low = (text or "").lower().replace("o ring", "o-ring")
    for w in list(extra_words) + PARTS:
        if w and re.search(r"(?<![a-z])" + re.escape(w.lower()) + r"(?![a-z])", low):
            return {"oring": "o-ring", "spider": "coupling", "alignment": "coupling", "lube": "lubrication"}.get(w.lower(), w.lower())
    words = [w for w in re.findall(r"[a-z]{4,}", low) if w not in ("assumed", "again", "found", "replaced", "checked", "faulty", "failed")]
    return " ".join(words[:2]) or "unknown"


def _similar(industry, asset, problem, code=None):
    """Past cases of this problem: same machine (weight 1), same model elsewhere (0.8), same type (0.4)."""
    q = _tok(problem)
    codes = set(re.findall(r"\b\d{3,5}\b", problem or "")) | ({str(code)} if code else set())
    out = []
    for r in store.records(industry):
        if r["status"] == "rejected" or r["outcome"] not in ("fixed", "temporary", "failed_again"):
            continue
        a = packs.asset(industry, r["asset_id"]) or {}
        if r["asset_id"] == asset.get("id"):
            w = 1.0
        elif asset.get("model") and a.get("model") == asset.get("model"):
            w = 0.8
        elif asset.get("type_key") and a.get("type_key") == asset.get("type_key"):
            w = 0.4
        else:
            continue
        rt = _tok(" ".join([r["problem"], r.get("symptom") or ""]))
        same_code = bool(codes and str(r.get("code") or "") in codes)
        overlap = len(q & rt) / max(1, min(len(q), len(rt)))
        if same_code or overlap >= 0.5:
            out.append((w * (1.0 if same_code else 0.8), r))
    return out


def causes(industry, asset, problem, code=None):
    """What it usually is, from this team's own history, and the smartest order to check."""
    cases = _similar(industry, asset, problem, code)
    if not cases:
        return None
    comp_words = [c["name"].split()[-1] for c in asset.get("components") or [] if c.get("name")]
    groups = defaultdict(lambda: {"score": 0.0, "fixed": 0, "failed": 0, "temporary": 0, "minutes": [], "people": set(),
                                  "last_fixed": None, "last_failed": None, "label": "", "label_w": 0, "refs": []})
    for w, r in cases:
        k = cause_key(r.get("cause") or r.get("action"), comp_words)
        g = groups[k]
        wt = w * _recency(r["datetime"])
        if r["outcome"] == "fixed":
            g["score"] += wt
            g["fixed"] += 1
            g["minutes"].append(r["downtime_minutes"] or 0)
            g["last_fixed"] = max(g["last_fixed"] or "", r["datetime"][:10])
            if wt > g["label_w"]:  # the clearest description: from the best recent success
                g["label"], g["label_w"] = (r.get("cause") or r.get("action") or k), wt
        elif r["outcome"] == "temporary":
            g["score"] += 0.4 * wt
            g["temporary"] += 1
        else:
            g["failed"] += 1
            g["last_failed"] = max(g["last_failed"] or "", r["datetime"][:10])
        if not g["label"]:
            g["label"] = r.get("cause") or r.get("action") or k
        if r.get("person_id"):
            g["people"].add((packs.person(industry, r["person_id"]) or {}).get("name", r["person_id"]))
        g["refs"].append(r["id"])
    # smoothing: a small "something else" share so 1–2 cases never look like 100 %
    alpha = 0.5
    total = sum(g["score"] for g in groups.values()) + alpha * (len(groups) + 1)
    all_minutes = [m for g in groups.values() for m in g["minutes"] if m]
    default_min = statistics.median(all_minutes) if all_minutes else 60
    rows = []
    for k, g in groups.items():
        p = (g["score"] + alpha) / total
        mins = statistics.median(g["minutes"]) if g["minutes"] else None
        faded = bool(g["last_failed"] and (not g["last_fixed"] or g["last_failed"] > g["last_fixed"]) and g["failed"] >= 1)
        rows.append({"cause": k, "label": re.sub(r"^(assumed|found)\s+", "", g["label"], flags=re.I)[:90], "p": round(p, 3),
                     "fixed": g["fixed"], "failed": g["failed"], "temporary": g["temporary"],
                     "minutes": round(mins) if mins else None, "time_known": mins is not None,
                     "people": sorted(g["people"])[:3], "last_fixed": g["last_fixed"], "faded": faded, "refs": g["refs"][-4:]})
    rows.sort(key=lambda x: -x["p"])
    other = round(alpha / total, 3)
    # smartest order: best chance per minute first — this order gives the shortest average time to the real cause
    t = lambda x: x["minutes"] or default_min  # noqa: E731
    order = sorted([x for x in rows if x["fixed"] or x["temporary"]], key=lambda x: -(x["p"] / max(t(x), 1)))
    never = [x for x in rows if not (x["fixed"] or x["temporary"])]

    def expected(seq):
        acc, done = 0.0, 0.0
        for x in seq:
            done += t(x)
            acc += x["p"] * done
        return acc + (1 - sum(x["p"] for x in seq)) * done
    smart = expected(order)
    worst = expected(sorted(order, key=lambda x: -t(x)))
    n = len(cases)
    return {"cases": n, "confidence": "low" if n < 3 else "medium" if n < 8 else "good", "causes": rows[:6], "other": other,
            "check_order": [{"cause": x["cause"], "label": x["label"], "p": x["p"], "minutes": t(x), "time_known": x["time_known"]}
                            for x in order[:5]],
            "dont_start_with": [{"cause": x["cause"], "label": x["label"], "failed": x["failed"]} for x in never if x["failed"]][:3],
            "expected_minutes": round(smart), "expected_minutes_worst_order": round(worst),
            "how": "From this team's past cases of the same problem on this machine (weight 1), the same model elsewhere (0.8) "
                   "and the same type (0.4); newer cases count more; a small share is kept for 'something else'. "
                   "Check order = highest chance per minute first."}


def aging(industry, rec):
    """How fresh a remembered fix is: old and never re-confirmed fades; a fix that failed since loses trust."""
    if not rec or rec.get("outcome") != "fixed":
        return None
    k = cause_key(rec.get("cause") or rec.get("action"))
    later = [r for r in store.records(industry, rec["asset_id"]) if r["datetime"] > rec["datetime"] and r["status"] != "rejected"
             and (str(r.get("code") or "") == str(rec.get("code") or "") and rec.get("code") or r["problem"] == rec["problem"])]
    failed_since = sum(1 for r in later if r["outcome"] == "failed_again" and cause_key(r.get("cause") or r.get("action")) == k)
    confirmed_since = [r for r in later if r["outcome"] == "fixed" and cause_key(r.get("cause") or r.get("action")) == k]
    last = (confirmed_since[-1]["datetime"] if confirmed_since else rec["datetime"])[:10]
    age = _days_ago(last)
    if failed_since >= 2:
        return {"level": "faded", "label": f"⏳ Failed {failed_since} times since — trust lowered", "weight": 0.3}
    if failed_since == 1:
        return {"level": "old", "label": "⏳ Failed once since — check before relying on it", "weight": 0.6}
    if age > 730:
        return {"level": "old", "label": f"⏳ Not re-confirmed since {last[:4]}", "weight": round(_recency(last), 2)}
    if confirmed_since:
        return {"level": "fresh", "label": f"✔ Re-confirmed {len(confirmed_since)}× since, last {last}", "weight": 1.0}
    return None


def cost_incidents(industry, asset_id=None, limit=12):
    """Repairs where the team's known fix was already in memory, but something else was tried first."""
    pk = packs.get(industry)
    out = []
    recs = [r for r in store.records(industry) if r["status"] != "rejected"]
    for r in recs:
        if r["outcome"] not in ("failed_again", "temporary") or (asset_id and r["asset_id"] != asset_id):
            continue
        a = packs.asset(industry, r["asset_id"]) or {}
        known = [x for x in recs if x["outcome"] == "fixed" and x["datetime"] < r["datetime"]
                 and (str(x.get("code") or "") == str(r.get("code") or "") and r.get("code") or x["problem"] == r["problem"])
                 and (x["asset_id"] == r["asset_id"] or (a.get("model") and (packs.asset(industry, x["asset_id"]) or {}).get("model") == a.get("model")))
                 and cause_key(x.get("cause") or x.get("action")) != cause_key(r.get("cause") or r.get("action"))]
        if not known:
            continue
        k = known[-1]
        hours = round((r["downtime_minutes"] or 0) / 60, 1)
        money = round(hours * a.get("cost_per_hour", pk.get("cost_per_hour", 0)) + (r.get("cost") or 0))
        out.append({"date": r["datetime"][:10], "asset_id": r["asset_id"], "problem": r["problem"], "tried": r["action"][:90],
                    "known_fix": k["action"][:90], "known_from": f"{k['asset_id']} on {k['datetime'][:10]}",
                    "known_by": (packs.person(industry, k["person_id"]) or {}).get("name", ""), "hours": hours, "money": money,
                    "record": r["id"]})
    out.sort(key=lambda x: x["date"], reverse=True)
    return {"incidents": out[:limit], "hours": round(sum(x["hours"] for x in out), 1), "money": sum(x["money"] for x in out),
            "count": len(out), "currency": "₹"}


def patterns(industry, aid):
    """The pattern detective: everything on one timeline, then the rhythms nobody noticed."""
    a = packs.asset(industry, aid)
    recs = [r for r in store.records(industry, aid) if r["status"] != "rejected"]
    events = [{"date": r["datetime"][:10], "time": r["datetime"][11:16], "kind": "sensor" if r.get("source") == "sensor" else "problem",
               "title": r["problem"], "code": r.get("code") or "", "outcome": r["outcome"], "action": r["action"][:80],
               "part": r.get("parts") or "", "minutes": r["downtime_minutes"] or 0} for r in recs]
    for s in stops(industry, aid):
        events.append({"date": s["at"][:10], "time": s["at"][11:16], "kind": "stop", "title": STOP_REASONS.get(s["reason"], s["reason"]),
                       "outcome": "", "action": s.get("note", ""), "minutes": s["minutes"], "code": "", "part": ""})
    events.sort(key=lambda e: (e["date"], e["time"]))
    findings = []
    by_problem = defaultdict(list)
    for r in recs:
        by_problem[str(r.get("code") or "") or r["problem"].lower()].append(r)
    for k, rs in by_problem.items():
        dates = sorted({r["datetime"][:10] for r in rs})
        if len(dates) >= 3:
            gaps = [(date.fromisoformat(b) - date.fromisoformat(x)).days for x, b in zip(dates, dates[1:])]
            med = statistics.median(gaps)
            findings.append({"kind": "rhythm", "text": f"“{rs[0]['problem']}” came back {len(dates)} times, about every {round(med)} days.",
                             "evidence": len(dates), "suggest": f"Check it every {max(7, round(med * 0.8))} days, before it comes back."})
        # what stopped it: after a fix with a part change, how long until it came back?
        fixes = [r for r in rs if r["outcome"] == "fixed"]
        for f in fixes:
            nxt = [r for r in rs if r["datetime"] > f["datetime"]]
            if nxt and f.get("parts"):
                gap = (datetime.fromisoformat(nxt[0]["datetime"][:19]) - datetime.fromisoformat(f["datetime"][:19])).days
                if gap >= 14:
                    findings.append({"kind": "part-life", "text": f"After “{f['parts']}” was replaced on {f['datetime'][:10]}, "
                                                                 f"“{f['problem']}” stayed away for {gap} days.",
                                     "evidence": 2, "suggest": f"Replace {f['parts'].lower()} every ~{round(gap * 0.9)} days."})
            elif not nxt and f.get("parts") and _days_ago(f["datetime"]) >= 30:
                findings.append({"kind": "fixed-for-good", "text": f"Since “{f['action'][:60]}” on {f['datetime'][:10]}, "
                                                                  f"“{f['problem']}” hasn't come back ({_days_ago(f['datetime'])} days).",
                                 "evidence": 1, "suggest": "This fix looks like the real cure."})
        failed_first = [r for r in rs if r["outcome"] == "failed_again"]
        if len(failed_first) >= 2 and fixes:
            findings.append({"kind": "repeat-mistake", "text": f"“{failed_first[0]['action'][:60]}” was tried {len(failed_first)} times "
                                                              f"and didn't work; “{fixes[-1]['action'][:60]}” did.",
                             "evidence": len(failed_first) + 1, "suggest": "Skip the first; Ustaad warns about it in answers."})
    hours = [int(r["datetime"][11:13]) for r in recs if len(r["datetime"]) >= 13 and r["datetime"][11:13].isdigit()]
    if len(hours) >= 6:
        night = sum(1 for h in hours if h >= 22 or h < 6)
        if night / len(hours) >= 0.4:
            findings.append({"kind": "shift", "text": f"{round(100 * night / len(hours))}% of problems start in the night shift (10 pm–6 am).",
                             "evidence": len(hours), "suggest": "Check what changes at night: operator, load, temperature."})
        days = Counter(datetime.fromisoformat(r["datetime"][:19]).strftime("%A") for r in recs)
        top, n = days.most_common(1)[0]
        if n / len(recs) >= 0.35 and n >= 3:
            findings.append({"kind": "weekday", "text": f"{n} of {len(recs)} problems started on a {top}.", "evidence": n,
                             "suggest": "Start-up after the weekend is a common cause — check the Monday start routine."
                             if top == "Monday" else f"Look at what's different on {top}s: shift, load, deliveries, cleaning."})
    return {"asset": {"id": aid, "name": (a or {}).get("name")}, "events": events[-60:], "findings": findings[:8]}


# ---------- sensors vs the maker's limits ----------
def maker_limits(a):
    """Max temperature / vibration from the maker's documents (report working window, specs)."""
    out = {}
    for x in ((a.get("report") or {}).get("operating_window") or []):
        what, rng = (x.get("what") or "").lower(), str(x.get("range") or "")
        nums = [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", rng)]
        if not nums:
            continue
        cite = f"manual p.{x['page']}" if x.get("page") else "maker's documents"
        if "temp" in what and "temp" not in out:
            out["temp"] = {"max": max(nums), "text": f"{cite} says max {max(nums):g} °C", "page": x.get("page")}
        if "vibrat" in what and "vib" not in out:
            out["vib"] = {"max": max(nums), "text": f"{cite} says max {max(nums):g} mm/s", "page": x.get("page")}
    return out


# ---------- downtime reasons + uptime ----------
def stops(industry, aid):
    return (store.meta_get(f"stops:{industry}:{aid}") or {}).get("list") or []


def log_stop(industry, aid, reason, minutes, note="", person_id=""):
    if not packs.asset(industry, aid):
        raise ValueError("Unknown item")
    if reason not in STOP_REASONS:
        raise ValueError("Pick a reason")
    minutes = max(1, min(int(float(minutes or 0)), 24 * 60))
    lst = stops(industry, aid)[-499:] + [{"at": datetime.now().isoformat(timespec="minutes"), "reason": reason, "minutes": minutes,
                                          "note": (note or "").strip()[:300], "person": person_id or ""}]
    store.meta_set(f"stops:{industry}:{aid}", {"list": lst})
    return lst[-1]


def uptime(industry, aid, days=30):
    pk = packs.get(industry)
    hours_per_day = pk.get("hours_per_day", 16)
    since = (datetime.now() - timedelta(days=days)).isoformat()
    by = Counter()
    for s in stops(industry, aid):
        if s["at"] >= since:
            by[s["reason"]] += s["minutes"]
    logged = [r for r in store.records(industry, aid) if r["datetime"] >= since and r["status"] != "rejected"]
    br = sum(r["downtime_minutes"] or 0 for r in logged)
    if br and not by.get("breakdown"):
        by["breakdown"] += br  # breakdowns logged as repairs count too
    lost = sum(by.values())
    planned = days * hours_per_day * 60
    return {"days": days, "uptime_pct": round(100 * max(0, 1 - lost / planned), 1), "lost_hours": round(lost / 60, 1),
            "planned_hours": round(planned / 60), "reasons": [{"reason": STOP_REASONS.get(k, k), "key": k, "hours": round(v / 60, 1)}
                                                              for k, v in by.most_common()],
            "money": round(lost / 60 * pk.get("cost_per_hour", 0))}


# ---------- part life by running hours ----------
def hour_meter(industry, aid):
    return (store.meta_get(f"hours:{industry}:{aid}") or {}).get("list") or []


def log_hours(industry, aid, hours):
    if not packs.asset(industry, aid):
        raise ValueError("Unknown item")
    h = float(hours)
    lst = hour_meter(industry, aid)
    if lst and h < lst[-1]["hours"]:
        raise ValueError(f"The hour meter can't go back (last reading {lst[-1]['hours']:g} h)")
    lst = lst[-199:] + [{"date": date.today().isoformat(), "hours": h}]
    store.meta_set(f"hours:{industry}:{aid}", {"list": lst})
    return lst[-1]


def _hours_at(meter, day, a, industry):
    """Hour-meter value on a day: from readings (interpolated) or, without readings, estimated from the calendar."""
    if len(meter) >= 2:
        pts = [(date.fromisoformat(m["date"]), m["hours"]) for m in meter]
        d = date.fromisoformat(day)
        if d <= pts[0][0]:
            rate = (pts[-1][1] - pts[0][1]) / max(1, (pts[-1][0] - pts[0][0]).days)
            return max(0.0, pts[0][1] - rate * (pts[0][0] - d).days)
        for (d1, h1), (d2, h2) in zip(pts, pts[1:]):
            if d1 <= d <= d2:
                return h1 + (h2 - h1) * ((d - d1).days / max(1, (d2 - d1).days))
        rate = (pts[-1][1] - pts[-2][1]) / max(1, (pts[-1][0] - pts[-2][0]).days)
        return pts[-1][1] + rate * (d - pts[-1][0]).days
    per_day = packs.get(industry).get("hours_per_day", 16) * 0.85
    start = a.get("install_date") or (meter[0]["date"] if meter else None)
    base = meter[0]["hours"] if meter else 0
    if not start:
        return None
    return base + per_day * max(0, (date.fromisoformat(day) - date.fromisoformat(start[:10])).days)


def part_life(industry, a):
    """'Spindle belt: 1,900 of 2,000 h used' — life from the manual's part tree (hours), use from the hour meter."""
    meter = hour_meter(industry, a["id"])
    today = date.today().isoformat()
    now_h = meter[-1]["hours"] if meter else _hours_at(meter, today, a, industry)
    if now_h is None:
        return []
    out = []
    for g in a.get("part_tree") or []:
        for p in g["parts"]:
            m = re.search(r"(\d[\d,]*)\s*(?:h|hrs?|hours|operating hours)\b", str(p.get("interval") or ""), re.I)
            if not m:
                continue
            life = float(m.group(1).replace(",", ""))
            words = [w for w in re.findall(r"[a-z]{4,}", p["name"].lower())]
            last = None
            for r in store.records(industry, a["id"]):
                blob = (r.get("parts") or "") + " " + r.get("action", "")
                if r["outcome"] in ("fixed", "temporary") and any(w in blob.lower() for w in words) and "replac" in blob.lower():
                    last = r["datetime"][:10]
            start_h = _hours_at(meter, last, a, industry) if last else (meter[0]["hours"] if meter and not a.get("install_date") else 0)
            used = max(0.0, now_h - (start_h or 0))
            out.append({"part": p["name"], "life_hours": life, "used_hours": round(used), "pct": round(100 * used / life),
                        "since": last or a.get("install_date") or "start", "source": "hour meter" if len(meter) >= 2 else "estimated from the calendar",
                        "status": "overdue" if used >= life else "soon" if used >= 0.85 * life else "ok"})
    return sorted(out, key=lambda x: -x["pct"])
