"""
Clear Render logs: one short line for everything Ustaad does, so you can see what worked and what failed.

    [START]     what is switched on (never the keys themselves)
    [REQ]       every API call: method, path, status, time (and the error, if any)
    [ASK]       a question: machine, language, memories used, who wrote the answer, trust, time
    [FEEDBACK]  ✔ worked / ✖ didn't work
    [MEMORY]    Hindsight recall / save — and when it fell back to practice memory
    [AI]        each Groq / Sarvam call: ok or FAILED, with the reason
    [TRANSLATE] Sarvam translation: to which language, how much text, ok or FAILED
    [VOICE-IN]  speech to text (written in voice.py)       [VOICE-OUT] text to speech
    [OCR]       Sarvam Vision (written in ocr.py)          [READ]      reading a manual / link / photo
    [EXPERT]    the expert read of a manual, start to end  [LOGBOOK] [VIDEO] [BRIEF] [MCP] [BACKUP]
    [ERROR]     anything that crashed, with where

install() wraps the existing functions from outside, so the features themselves are unchanged.
Keys never reach the log: anything that looks like a key or a Bearer token is masked.
"""
import functools
import re
import time

_SECRET = re.compile(r"\b(gsk_|hsk_|ghp_|gho_|github_pat_|sk_)[A-Za-z0-9_\-]{6,}|Bearer\s+\S+", re.I)


def clean(x, n=160):
    s = re.sub(r"\s+", " ", str(x if x is not None else "")).strip()
    return _SECRET.sub("***", s)[:n]


def log(tag, msg):
    print(f"[{tag}] {clean(msg, 400)}", flush=True)


def _q(text, n=60):
    t = clean(text, n + 1)
    return f'"{t[:n]}…"' if len(t) > n else f'"{t}"'


def _wrap(owner, name, tag, describe, fail=None):
    """Replace owner.name with a timed copy that logs one line. describe(result, args, kwargs, seconds) -> text."""
    fn = getattr(owner, name, None)
    if fn is None or getattr(fn, "_logged", False):
        return

    @functools.wraps(fn)
    def run(*a, **k):
        t = time.perf_counter()
        try:
            out = fn(*a, **k)
        except Exception as e:
            log(tag, f"{name} FAILED after {time.perf_counter() - t:.1f}s — {type(e).__name__}: {e}")
            raise
        try:
            text = describe(out, a, k, time.perf_counter() - t)
            if text:
                log(tag, text)
        except Exception:  # a log line must never break the feature
            pass
        return out
    run._logged = True
    setattr(owner, name, run)


def install():
    from . import agent, backup, daily, expert, knowhow, lang, llm, machines, mcp_server, memory, network

    # ---- AI brains ----
    def ai(who):
        return lambda out, a, k, s: f"{who} {'ok' if out is not None else 'FAILED'} in {s:.1f}s" + \
            ("" if out is not None else f" — {llm.last_error or 'no answer'}")
    _wrap(llm, "_groq_json", "AI", ai("Groq (writing)"))
    _wrap(llm, "_sarvam_json", "AI", ai("Sarvam-105B (writing)"))
    _wrap(llm, "vision_json", "AI", ai("Groq vision (photo)"))
    _wrap(llm, "_custom_json", "AI", ai("Your own AI (writing)"))
    _wrap(llm, "speak", "VOICE-OUT", lambda out, a, k, s:
          f"{k.get('language') or (a[1] if len(a) > 1 else 'en')} | {len(a[0] if a else k.get('text') or '')} chars | "
          + (f"spoken by Sarvam in {s:.1f}s" if out else f"FAILED in {s:.1f}s — {llm.last_error or 'Sarvam key missing'}"))

    # ---- translation ----
    _wrap(lang, "translate_texts", "TRANSLATE", lambda out, a, k, s:
          f"→ {a[1] if len(a) > 1 else k.get('target')} | {sum(len(x) for x in (a[0] if a else []) if isinstance(x, str))} chars | "
          + (f"Sarvam ok in {s:.1f}s" if out is not None else f"FAILED — {lang.last_error or 'Sarvam key missing'}"))

    # ---- memory (Hindsight) ----
    def recall(out, a, k, s):
        svc = a[0]
        src = "Hindsight" if svc.cloud and not svc.last_error else "practice memory"
        why = f" — {svc.last_error}" if svc.last_error else ""
        return f"recall {a[1]} {_q(a[2], 50)} → {len(out)} found from {src} in {s:.1f}s{why}"
    _wrap(memory.MemoryService, "recall", "MEMORY", recall)
    cloud = getattr(memory, "HindsightMemory", None)
    if cloud:
        _wrap(cloud, "retain", "MEMORY", lambda out, a, k, s: f"saved 1 memory to Hindsight ({a[1]}) in {s:.1f}s")
        _wrap(cloud, "retain_batch", "MEMORY", lambda out, a, k, s: f"saved {len(a[2])} memories to Hindsight ({a[1]}) in {s:.1f}s")

    # ---- asking and learning ----
    def ask(out, a, k, s):
        if out.get("mode") != "answer":
            return f"{a[0]} | chart request | {s:.1f}s"
        used = sum(1 for m in out.get("memories") or [] if m.get("used"))
        bits = [a[0], out["asset"]["id"], f"lang={out.get('language')}", _q(out.get("problem_en") or out.get("problem"), 50),
                f"{used} memories used", f"written by {out.get('written_by')}", f"trust: {(out.get('trust') or {}).get('label', '')}"]
        if out.get("translated_by"):
            bits.append(f"translated by {out['translated_by']}")
        if out.get("diagnosis"):
            top = (out["diagnosis"].get("causes") or [{}])[0]
            bits.append(f"top cause {top.get('label', '?')} {round((top.get('p') or 0) * 100)}%")
        for e in ("memory_error", "llm_error"):
            if out.get(e):
                bits.append(f"{e.split('_')[0]} problem: {out[e]}")
        return " | ".join(str(b) for b in bits) + f" | {s:.1f}s"
    _wrap(agent, "ask", "ASK", ask)
    _wrap(agent, "feedback", "FEEDBACK", lambda out, a, k, s:
          f"{a[0]} | ask {a[1]} | {'✔ worked' if a[2] == 'fixed' else '✖ did not work'} | saved to {out.get('saved_to')}"
          + (f" | credit to {out['credited_to']}" if out.get("credited_to") else "")
          + (f" | call {out['expert']['name']}" if out.get("expert") else ""))
    _wrap(agent, "smart_log", "LOG", lambda out, a, k, s: f"{a[0]} | {_q(a[1], 50)} | {s:.1f}s")
    _wrap(agent, "add_tip", "LOG", lambda out, a, k, s: f"{a[0]} | tip for {a[2]} | {s:.1f}s")

    # ---- reading manuals ----
    def read(out, a, k, s):
        src = "file " + _q(k["file"][1], 40) if k.get("file") else "link " + _q(k.get("url"), 60) if k.get("url") else "text"
        rd = out.get("read") or {}
        srcs = rd.get("sources") or []
        pages = sum(int(x.get("kept_pages") or 0) for x in srcs)
        ocr = sum(int(x.get("ocr_pages") or 0) for x in srcs)
        c = out.get("spec_counts") or {}
        return (f"{a[0]} | from {src} | model {out.get('model') or '?'} | {pages} pages, {ocr} read by Sarvam Vision | "
                f"{rd.get('rows_found', 0)} table rows | specs: " + ", ".join(f"{v} {k2}" for k2, v in c.items()) + f" | {s:.1f}s")
    _wrap(machines, "read_source", "READ", read)

    def exp(out, a, k, s):
        if out.get("state") == "failed":
            return f"{a[1]} FAILED after {s:.0f}s — {out.get('error')}"
        return f"{a[1]} done in {s:.0f}s | {out.get('total', 0)} sections"
    _wrap(expert, "build", "EXPERT", exp)
    _wrap(expert, "start", "EXPERT", lambda out, a, k, s: f"{a[1]} expert read started in the background")

    # ---- know-how capture ----
    _wrap(knowhow, "logbook_read", "LOGBOOK", lambda out, a, k, s:
          f"{a[0]} | read by {out.get('read_by')} | {len(out.get('entries') or [])} entries | split by {out.get('written_by')} | {s:.1f}s")
    _wrap(knowhow, "logbook_save", "LOGBOOK", lambda out, a, k, s: f"{a[0]} | {out.get('saved')} entries saved (waiting for approval)")
    _wrap(knowhow, "video_guide", "VIDEO", lambda out, a, k, s:
          f"{a[0]} | {out.get('asset_id')} | {_q(out.get('title'), 40)} | {len(out.get('steps') or [])} steps | {s:.1f}s")
    _wrap(knowhow, "save_guide", "VIDEO", lambda out, a, k, s: f"{a[0]} | guide {out.get('id')} saved | memory: {out.get('memory')}")

    # ---- the machine calls first / other plants ----
    _wrap(machines, "sensor_alert", "ALERT", lambda out, a, k, s:
          f"{a[0]} | {a[1]} | {'NEW case ' + out['record']['id'] if out.get('new') else 'already open ' + out['record']['id']}"
          + (f" | {(out.get('plan') or {}).get('what')} {(out.get('plan') or {}).get('value')}" if out.get("plan") else "")
          + (f" | best person: {out['plan']['expert']['name']}" if (out.get("plan") or {}).get("expert") else " | no expert found"))
    _wrap(network, "share", "NETWORK", lambda out, a, k, s: f"{a[0]} | shared 1 fix with other plants (names removed)" if out else None)
    _wrap(network, "set_share", "NETWORK", lambda out, a, k, s: f"{a[0]} | sharing turned {'ON' if out['share'] else 'OFF'}")

    # ---- daily use ----
    _wrap(daily, "briefing", "BRIEF", lambda out, a, k, s:
          f"{a[0]} | lang={out.get('language')} | {len(out.get('items') or [])} items"
          + (f" | translated by {out['translated_by']}" if out.get("translated_by") else "") + f" | {s:.1f}s")

    # ---- other AIs ----
    def mcp(out, a, k, s):
        m = a[0] if a and isinstance(a[0], dict) else {}
        meth = m.get("method")
        if out is None:
            return f"{meth} (notification)"
        if meth == "tools/call":
            p = m.get("params") or {}
            bad = (out.get("result") or {}).get("isError")
            return f"tools/call {p.get('name')} {'FAILED' if bad else 'ok'} in {s:.1f}s" + \
                (f" — {clean(out['result']['content'][0]['text'], 120)}" if bad else "")
        return f"{meth} {'error: ' + out['error']['message'] if out.get('error') else 'ok'}"
    _wrap(mcp_server, "handle", "MCP", mcp)

    # ---- auto-save ----
    _wrap(backup, "save_now", "BACKUP", lambda out, a, k, s:
          f"saved to GitHub in {s:.1f}s" if out else (f"save FAILED — {backup.state.get('last_error')}" if backup.state.get("last_error") else None))
    _wrap(backup, "restore", "BACKUP", lambda out, a, k, s:
          None if not backup.state.get("enabled") else
          f"loaded {out} saved items from GitHub" if out is not None else f"load FAILED — {backup.state.get('last_error')}")


def startup():
    import shutil
    from . import backup, config, llm, memory
    on = lambda x: "✓" if x else "✗"  # noqa: E731
    try:
        mem = memory.memory.mode if hasattr(memory, "memory") else ("Hindsight" if config.HINDSIGHT_API_KEY else "practice")
    except Exception:
        mem = "?"
    try:
        saving = "GitHub ✓" if backup.state.get("enabled") else "off (no GITHUB_TOKEN / GITHUB_REPO)"
    except Exception:
        saving = "?"
    import os
    writers = " → ".join(n for n, _ in llm.writers()) or "rules (no AI key)"
    log("START", f"Ustaad ready | memory: {mem} | answers written by: {writers} | Sarvam {on(llm.sarvam_available())} "
                 f"(voice, translate, OCR, speech) | ffmpeg {on(shutil.which('ffmpeg'))} | auto-save: {saving} | "
                 f"MCP at /mcp ({'locked with MCP_TOKEN' if os.getenv('MCP_TOKEN', '').strip() else 'open'})")
