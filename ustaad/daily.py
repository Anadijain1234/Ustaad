"""
Daily use + AI access (Stage 5):
  briefing()          the morning voice briefing — what needs attention today, in plain sentences (no AI needed)
  machine_markdown()  one readable summary file per machine, for people and for other AIs (like a skills.md)
  llms_txt()          what Ustaad is and where everything is, for AI assistants (the llms.txt convention)
"""
from datetime import date, datetime, timedelta

from . import diagnosis, insights, lang, machines, packs, specs, store


def briefing(industry, site=None, language="en"):
    pk = packs.get(industry)
    L = pk["labels"]
    assets = [a for a in packs.assets(industry) if not site or a.get("site") == site]
    today = date.today()
    lines, items = [], []
    # 0) machines that called (sensor alert, still open): first thing anyone should hear
    for al in machines.open_alerts(industry):
        if not any(al["asset_id"] == a["id"] for a in assets):
            continue
        who = al.get("expert") or {}
        lines.append(f"Alert: {al['asset_id']} called — {al['what'].lower()}, {al['value']}."
                     + (f" {who['name']} is the best person for it." if who.get("name") else "")
                     + (f" Last time, this worked: {al['last_fix']['action'][:90].rstrip('.')}." if al.get("last_fix") else ""))
        items.append({"kind": "alert", "asset_id": al["asset_id"], "text": lines[-1]})
    # 1) overdue / due service
    due = []
    for a in assets:
        for x in machines.service_due(industry, a):
            if x["status"] in ("overdue", "soon") and x["days_left"] <= 1:
                due.append((a["id"], x))
    for aid, x in due[:4]:
        lines.append(f"{aid}: {x['what'].replace('Replace / check ', 'check or replace the ').lower()} — {'due today' if x['days_left'] >= 0 else str(-x['days_left']) + ' days overdue'}.")
        items.append({"kind": "service", "asset_id": aid, "text": lines[-1]})
    # 2) parts out of stock
    out = [(a["id"], c) for a in assets for c in a.get("components") or [] if c.get("stock") == 0]
    if out:
        names = ", ".join(f"{c['name']} for {aid}" for aid, c in out[:3])
        lines.append(f"Out of stock: {names}. Order today.")
        items.append({"kind": "parts", "text": lines[-1]})
    # 3) what went wrong in the last day, and what's still open
    since = (datetime.now() - timedelta(hours=30)).isoformat()
    recent = [r for r in store.records(industry) if r["datetime"] >= since and r["status"] != "rejected" and r.get("source") != "sensor"
              and any(r["asset_id"] == a["id"] for a in assets)]
    by_asset = {}
    for r in recent:
        by_asset.setdefault(r["asset_id"], []).append(r)
    for aid, rs in list(by_asset.items())[:3]:
        prob = rs[-1]["problem"]
        n = len(rs)
        lines.append(f"{aid} had {prob.lower()}{' ' + str(n) + ' times' if n > 1 else ''} yesterday" +
                     (" — still open." if rs[-1]["outcome"] == "open" else " — fixed." if rs[-1]["outcome"] == "fixed" else "."))
        items.append({"kind": "yesterday", "asset_id": aid, "text": lines[-1]})
    opened = [r for r in store.records(industry) if r["outcome"] == "open" and r["status"] != "rejected"
              and any(r["asset_id"] == a["id"] for a in assets) and r["datetime"] < since]
    if opened:
        lines.append(f"{len(opened)} older problem(s) are still open, like {opened[-1]['asset_id']}: {opened[-1]['problem'].lower()}.")
        items.append({"kind": "open", "text": lines[-1]})
    # 4) what is likely to come back soon (from the repeat-problem rhythm)
    try:
        for r in insights.repeat_failures(industry)["repeat"][:5]:
            nxt = r.get("next_expected")
            if nxt and 0 <= (date.fromisoformat(nxt) - today).days <= 3 and any(r["asset_id"] == a["id"] for a in assets):
                lines.append(f"Watch {r['asset_id']}: {r['problem'].lower()} usually comes back around now. Check it early.")
                items.append({"kind": "repeat", "asset_id": r["asset_id"], "text": lines[-1]})
                break
    except Exception:
        pass
    # 5) parts near the end of their life by running hours
    for a in assets:
        for p in diagnosis.part_life(industry, a)[:1]:
            if p["status"] in ("soon", "overdue"):
                lines.append(f"{a['id']}: {p['part']} has used {p['pct']}% of its life. Plan the change.")
                items.append({"kind": "life", "asset_id": a["id"], "text": lines[-1]})
    site_name = (packs.site(industry, site) or {}).get("name") if site else None
    hello = f"Good morning{', ' + site_name if site_name else ''}. Here is today's {L['asset'].lower()} briefing."
    if not lines:
        lines = [f"All {L['assets'].lower()} look fine. Nothing overdue, nothing open. Have a safe shift."]
    lines = lines[:7]
    text = " ".join([hello] + lines + ["Ask Ustaad if something looks wrong. Have a safe shift."])
    shown = text
    by = None
    if language != "en":
        t = lang.translate_texts([text], language)
        if t:
            shown, by = t[0], "Sarvam"
    return {"text": shown, "text_en": text, "items": items, "language": language, "translated_by": by,
            "date": today.isoformat(), "site": site_name}


def machine_markdown(industry, aid):
    """Everything worth knowing about one machine, as a plain Markdown file (readable by people and by AIs)."""
    a = packs.asset(industry, aid)
    if not a:
        raise ValueError("Unknown item")
    pk = packs.get(industry)
    p = machines.profile(industry, aid)
    name = a.get("name", "")
    name = name[len(aid):].lstrip(" ·:—-") if name.startswith(aid) else name
    out = [f"# {aid} — {name}", "",
           f"- Organisation: {pk['org']['name']} ({pk['name']})", f"- Site: {p.get('site') or a.get('site', '')}",
           f"- Maker / model: {a.get('maker', '') or '—'} / {a.get('model', '') or '—'}", f"- Type: {a.get('type', '')}",
           f"- Health today: {p['health']['level']} — {'; '.join(p['health']['reasons'])}", ""]
    if p.get("spec_fields"):
        out += ["## Key specs (checked against the maker's documents)", ""]
        out += [f"- {f['label']}: {specs.show(f)} ({f.get('status')})" for f in p["spec_fields"] if f.get("value")] + [""]
    elif a.get("specs"):
        out += ["## Specs", ""] + [f"- {s['label']}: {s['value']}" for s in a["specs"]] + [""]
    r = a.get("report") or {}
    if r.get("summary"):
        out += ["## Expert report", "", r["summary"], ""]
        if r.get("likely_failures"):
            out += ["What will probably break first:"] + [f"- {x.get('part')}: {x.get('why', '')}" for x in r["likely_failures"][:5]] + [""]
    if p.get("service_due"):
        out += ["## Service due", ""] + [f"- {x['what']}: {x['status']} ({x['days_left']} days)" for x in p["service_due"]] + [""]
    if p.get("parts"):
        out += ["## Spare parts", ""] + [f"- {c['name']} {c.get('part_no', '')}: {c.get('stock', '?')} in store" for c in p["parts"]] + [""]
    fixes = [h for h in p.get("history", []) if h["outcome"] == "fixed"][:8]
    if fixes:
        out += ["## Fixes that worked (newest first)", ""]
        out += [f"- {h['date']} · {h['problem']}: {h['action']} — {h['person']}" for h in fixes] + [""]
    failed = [h for h in p.get("history", []) if h["outcome"] == "failed_again"][:5]
    if failed:
        out += ["## Tried and did NOT work — don't repeat", ""] + [f"- {h['date']} · {h['problem']}: {h['action']}" for h in failed] + [""]
    if p.get("experts"):
        out += ["## Who knows it best", ""] + [f"- {x['name']} ({x.get('role', '')})" for x in p["experts"][:4]] + [""]
    out += ["---", f"Generated by Ustaad on {datetime.now():%d %b %Y %H:%M}. Ask more through the API or the MCP server at /mcp."]
    return "\n".join(out)


def llms_txt(base_url):
    lines = ["# Ustaad", "",
             "> Expert memory for factories, kitchens, hospitals, garages and IT teams: what experts did, whether it worked, "
             "and who did it — by voice, in Indian languages.", "",
             "## For AI assistants", f"- MCP server (Streamable HTTP, JSON-RPC): {base_url}/mcp",
             f"- API list: {base_url}/api/endpoints", f"- System status: {base_url}/api/system", "",
             "## Machine summaries (Markdown)"]
    for ind in packs.ids():
        for a in packs.assets(ind)[:30]:
            lines.append(f"- [{ind} {a['id']} — {a.get('name', '')}]({base_url}/machines/{ind}/{a['id']}.md)")
    return "\n".join(lines) + "\n"
