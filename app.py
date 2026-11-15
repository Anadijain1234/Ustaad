"""
Ustaad — the expert who never leaves.
One expert-memory engine (Hindsight + Groq) with industry packs: factory, restaurant, hospital operations,
car garage and IT on-call. Run locally:  python app.py   →  http://localhost:5000
"""
import base64
import json
import time
from pathlib import Path
import os

from flask import Flask, jsonify, redirect, request, send_from_directory

from ustaad import agent, backup, benchmark, config, custom, daily, diagnosis, expert, insights, knowhow, mcp_server, llm, machines, network, packs, store, voice
from ustaad.memory import memory
from ustaad import logs

logs.install()  # clear one-line Render logs for every feature (see ustaad/logs.py)
app = Flask(__name__, static_folder="static", static_url_path="/static")
BASE = Path(__file__).resolve().parent
app.config["MAX_CONTENT_LENGTH"] = 48 * 1024 * 1024  # manuals and short fix videos
store.init()


def ok(data):
    return jsonify(data)


def err(msg, code=400):
    return jsonify({"error": str(msg)}), code


@app.errorhandler(ValueError)
def _value_error(e):
    return err(e, 400)


@app.errorhandler(PermissionError)
def _perm_error(e):
    return err(e, 403)


def body():
    return request.get_json(silent=True) or {}


# ---------- one log line per API call ----------
QUIET = ("/api/status", "/api/ui-translate", "/api/system")  # polled often: only logged when they fail


@app.before_request
def _t0():
    request.environ["ustaad.t0"] = time.perf_counter()


@app.after_request
def _req_log(resp):
    path = request.path
    quiet = path.startswith(QUIET) or path.endswith("/alerts")
    if (path.startswith("/api/") or path == "/mcp" or path.startswith("/machines/")) and not (quiet and resp.status_code < 400):
        took = time.perf_counter() - request.environ.get("ustaad.t0", time.perf_counter())
        why = ""
        if resp.status_code >= 400 and resp.is_json:
            why = " | " + str((resp.get_json(silent=True) or {}).get("error") or "")
        logs.log("REQ", f"{request.method} {path} → {resp.status_code} in {took:.1f}s{why}")
    return resp


from flask import got_request_exception  # noqa: E402


def _crash(sender, exception, **extra):
    logs.log("ERROR", f"{request.method} {request.path} | {type(exception).__name__}: {exception}")


got_request_exception.connect(_crash, app)


def _ind(industry):
    packs.get(industry)  # raises ValueError if unknown
    return industry


# ---------- pages ----------
@app.get("/")
def index():
    return send_from_directory("static", "index.html")


@app.get("/p/<industry>/<person_id>")
def passport_link(industry, person_id):
    return redirect(f"/#/passport/{industry}/{person_id}" + ("/private" if request.args.get("private") == "1" else ""))


@app.get("/m/<industry>/<asset_id>")
def machine_link(industry, asset_id):  # the QR sticker on a machine points here
    return redirect(f"/#/m/{industry}/{asset_id}")


@app.get("/health")
def health():
    return ok({"ok": True})


# ---------- general ----------
@app.get("/api/status")
def status():
    return ok({"memory": memory.mode, "memory_error": memory.last_error, "llm": llm.available(),
               "llm_model": (llm.writers() or [(None, None)])[0][1], "writers": [n for n, _ in llm.writers()], "own_brain": llm.custom_available(),
               "groq": llm.groq_available(), "sarvam": llm.sarvam_available(), "llm_error": llm.last_error,
               "autosave": backup.status(), "voice": voice.status(),
               "banks": {i: config.bank_id(i) for i in packs.ids()}})


@app.get("/api/industries")
def industries():
    return ok({"industries": [packs.summary(i) for i in packs.ids()],
               "coming_soon": [{"name": "Farming", "icon": "🌾"}, {"name": "Hotels", "icon": "🏨"},
                               {"name": "Construction", "icon": "🏗️"}, {"name": "Aviation", "icon": "✈️"}]})


@app.post("/api/packs/custom")
def create_pack():
    b = body()
    out = custom.create(b.get("name"), b.get("description", ""))
    backup.mark_dirty()
    return ok(out)


@app.get("/api/i/<industry>/pack")
def pack(industry):
    p = packs.get(_ind(industry))
    return ok(packs.summary(industry) | {"assets": packs.assets(industry), "people": p["people"], "panels": p.get("panels", []),
                                         "checklists": p.get("checklists", []), "lookup": p.get("lookup")})


@app.post("/api/i/<industry>/ask")
def ask(industry):
    b = body()
    return ok(agent.ask(_ind(industry), b.get("asset_id"), b.get("problem"), bool(b.get("use_memory", True)), b.get("language", "en"),
                        b.get("expert_id") or None))


@app.post("/api/i/<industry>/feedback")
def feedback(industry):
    b = body()
    return ok(agent.feedback(_ind(industry), b.get("ask_id"), b.get("result"), b.get("person_id"), b.get("note", ""),
                             b.get("downtime_minutes"), b.get("action_done", ""), b.get("steps_done"), b.get("asset_id")))


@app.post("/api/i/<industry>/log")
def log(industry):
    return ok(agent.log_record(_ind(industry), body()))


@app.post("/api/i/<industry>/smart-log")
def smart_log(industry):
    b = body()
    return ok(agent.smart_log(_ind(industry), b.get("text"), b.get("person_id")))


@app.post("/api/i/<industry>/tips")
def tips(industry):
    b = body()
    return ok(agent.add_tip(_ind(industry), b.get("person_id"), b.get("asset_id", "ALL"), b.get("text"), b.get("source_ref", "")))


@app.get("/api/i/<industry>/memories")
def memories(industry):
    _ind(industry)
    from ustaad.memory import all_memories
    kind = request.args.get("kind")
    aid = request.args.get("asset_id")
    flagged = store.flagged_keys(industry)
    items = [m for m in all_memories(industry) if (not kind or m["kind"] == kind) and (not aid or m["asset_id"] in (aid, "ALL"))]
    items.sort(key=lambda m: m["timestamp"], reverse=True)
    cards = [agent.memory_card(industry, {**m, "origin": "store"}, "") | {"flagged": m["key"] in flagged} for m in items[:400]]
    return ok({"memories": cards, "total": len(items)})


@app.get("/api/i/<industry>/pending")
def pending(industry):
    return ok({"pending": store.pending(_ind(industry))})


@app.post("/api/i/<industry>/approve")
def approve(industry):
    b = body()
    return ok(agent.approve(_ind(industry), b.get("key"), b.get("role"), b.get("approver_id"), b.get("ok", True)))


@app.post("/api/i/<industry>/flag")
def flag(industry):
    b = body()
    if not b.get("key"):
        raise ValueError("Missing memory key")
    if b.get("unflag"):
        store.remove_flag(b["key"])
        return ok({"ok": True, "message": "Restored."})
    store.add_flag(_ind(industry), b["key"], b.get("reason", "wrong"), b.get("by", ""))
    return ok({"ok": True, "message": "Flagged — Ustaad will not use this memory any more."})


@app.get("/api/i/<industry>/flags")
def flags(industry):
    return ok({"flags": store.flags(_ind(industry))})


@app.get("/api/i/<industry>/problems")
def problems(industry):
    return ok({"problems": agent.problems_for(_ind(industry), request.args.get("asset_id"))})


@app.post("/api/i/<industry>/playbook")
def playbook(industry):
    b = body()
    return ok(agent.playbook(_ind(industry), b.get("asset_id"), b.get("problem"), b.get("language", "en")))


@app.get("/api/i/<industry>/risk")
def risk(industry):
    return ok(insights.knowledge_risk(_ind(industry)))


@app.get("/api/i/<industry>/interview")
def interview(industry):
    return ok(agent.interview(_ind(industry), request.args.get("person_id"), request.args.get("language", "en")))


@app.post("/api/i/<industry>/interview/answer")
def interview_answer(industry):
    b = body()
    return ok(agent.answer_interview(_ind(industry), b.get("person_id"), b.get("asset_id"), b.get("question"), b.get("answer")))


@app.get("/api/i/<industry>/shift-report")
def shift_report(industry):
    return ok(agent.shift_report(_ind(industry), int(request.args.get("hours", 24)), request.args.get("language", "en")))


@app.get("/api/i/<industry>/coverage")
def coverage(industry):
    return ok(insights.coverage(_ind(industry)))


@app.get("/api/i/<industry>/leaderboard")
def leaderboard(industry):
    return ok(insights.leaderboard(_ind(industry)))


@app.get("/api/i/<industry>/skills")
def skills(industry):
    return ok(insights.skill_map(_ind(industry)))


@app.get("/api/i/<industry>/passport/<person_id>")
def passport(industry, person_id):
    ind = _ind(industry)
    return ok(knowhow.passport_extra(ind, person_id, insights.passport(ind, person_id), request.args.get("private") == "1"))


@app.get("/api/i/<industry>/repeat")
def repeat(industry):
    return ok({"repeat": insights.repeat_failures(_ind(industry))})


@app.get("/api/i/<industry>/stats")
def stats(industry):
    return ok(insights.stats(_ind(industry)))


@app.get("/api/i/<industry>/cross-site")
def cross_site(industry):
    return ok({"links": insights.cross_site(_ind(industry))})


@app.get("/api/i/<industry>/quiz")
def quiz(industry):
    return ok(insights.quiz(_ind(industry), seed=request.args.get("seed")))


@app.post("/api/i/<industry>/photo")
def photo(industry):
    f = request.files.get("image")
    if not f:
        raise ValueError("No photo received")
    b64 = base64.b64encode(f.read()).decode()
    return ok(agent.read_photo(_ind(industry), b64, f.mimetype or "image/jpeg", request.form.get("asset_id")))


@app.post("/api/i/<industry>/reset")
def reset(industry):
    store.load_seed(_ind(industry))
    backup.mark_dirty()
    return ok({"ok": True, "message": "Demo data restored for this industry."})


@app.post("/api/translate")
def translate():
    b = body()
    return ok(agent.translate(b.get("texts") or [], b.get("language", "hi")))


@app.post("/api/voice")
def voice_in():
    f = request.files.get("audio")
    if not f:
        raise ValueError("No audio received")
    ind = request.form.get("industry") or ""
    r = voice.transcribe(f.read(), f.filename or "voice.webm", f.mimetype or "", request.form.get("language") or None,
                         ind if ind in packs.ids() else None)
    if not r["text"]:
        if not (config.SARVAM_API_KEY or llm.groq_available()) and not voice.ffmpeg():
            raise ValueError("Voice needs the Sarvam key")
        raise ValueError("Couldn't hear any words. Speak a little closer to the phone and try again.")
    return ok(r)


@app.post("/api/speak")
def speak():
    b = body()
    audio = llm.speak(b.get("text", ""), b.get("language", "en"))
    if not audio:
        raise ValueError("Speaking needs the Sarvam key" if not llm.sarvam_available() else f"Could not speak: {llm.last_error}")
    return ok({"audio": audio, "mime": "audio/wav"})


# ---------- My machines ----------
@app.get("/api/i/<industry>/machines")
def machine_list(industry):
    return ok({"machines": machines.summary_list(_ind(industry))})


@app.get("/api/i/<industry>/machines/<asset_id>")
def machine_profile(industry, asset_id):
    return ok(machines.profile(_ind(industry), asset_id))


@app.post("/api/i/<industry>/machines")
def machine_save(industry):
    b = body()
    return ok(machines.save(_ind(industry), b.get("machine") or {}, b.get("person_id"), b.get("role")))


@app.post("/api/i/<industry>/machines/read")
def machine_read(industry):
    """Fill the 'add machine' form from a web link, a PDF (even scanned), a photo or typed text — checked against the source."""
    _ind(industry)
    f = request.files.get("file")
    if f:
        return ok(machines.read_source(industry, file=(f.read(), f.filename or "upload", f.mimetype or ""),
                                       pages=request.form.get("pages")))
    b = body()
    return ok(machines.read_source(industry, url=b.get("url"), text=b.get("text"), pages=b.get("pages"),
                                   read_id=b.get("read_id"), model=b.get("model")))


@app.post("/api/i/<industry>/machines/<asset_id>/ask-manual")
def machine_ask_manual(industry, asset_id):
    return ok(machines.ask_manual(_ind(industry), asset_id, body().get("question")))


@app.get("/api/i/<industry>/machines/<asset_id>/service.ics")
def machine_ics(industry, asset_id):
    from flask import Response
    return Response(machines.service_ics(_ind(industry), asset_id), mimetype="text/calendar",
                    headers={"Content-Disposition": f"attachment; filename={asset_id}-service.ics"})


@app.get("/api/i/<industry>/machines/<asset_id>/report")
def machine_report(industry, asset_id):
    return ok(expert.view(_ind(industry), asset_id))


@app.post("/api/i/<industry>/machines/<asset_id>/report")
def machine_report_build(industry, asset_id):
    expert.start(_ind(industry), asset_id)
    return ok(expert.view(_ind(industry), asset_id))


@app.get("/api/i/<industry>/machines/<asset_id>/part/<pid>")
def machine_part(industry, asset_id, pid):
    return ok(expert.part(_ind(industry), asset_id, pid))


@app.get("/api/i/<industry>/machines/<asset_id>/vendor-message")
def machine_vendor_message(industry, asset_id):
    return ok({"text": expert.vendor_message(_ind(industry), asset_id)})


@app.get("/api/i/<industry>/machines/<asset_id>/page")
def machine_page(industry, asset_id):
    return ok(machines.manual_page(_ind(industry), asset_id, request.args.get("n", "0"), request.args.get("src")))


@app.post("/api/i/<industry>/machines/<asset_id>/photo-pages")
def machine_photo_pages(industry, asset_id):
    f = request.files.get("image")
    if not f:
        raise ValueError("No photo received")
    return ok(machines.photo_pages(_ind(industry), asset_id, f.read(), f.mimetype or "image/jpeg"))


@app.get("/api/i/<industry>/machines/<asset_id>/patterns")
def machine_patterns(industry, asset_id):
    return ok(diagnosis.patterns(_ind(industry), asset_id))


@app.post("/api/i/<industry>/machines/<asset_id>/stop")
def machine_stop(industry, asset_id):
    b, ind = body(), _ind(industry)
    stop = diagnosis.log_stop(ind, asset_id, b.get("reason"), b.get("minutes"), b.get("note", ""), b.get("person_id", ""))
    rec = None
    if b.get("reason") == "breakdown" and len((b.get("note") or "").strip()) >= 8:  # what did you do? -> it becomes a memory
        try:
            rec = agent.smart_log(ind, f"{asset_id}: {b['note']} (machine stopped {stop['minutes']} min)", b.get("person_id"))
        except Exception:
            rec = None
    return ok({"stop": stop, "memory": rec, "uptime": diagnosis.uptime(ind, asset_id)})


@app.post("/api/i/<industry>/machines/<asset_id>/hours")
def machine_hours(industry, asset_id):
    return ok({"reading": diagnosis.log_hours(_ind(industry), asset_id, body().get("hours"))})


@app.get("/api/i/<industry>/cost-of-not-asking")
def cost_of_not_asking(industry):
    return ok(diagnosis.cost_incidents(_ind(industry), None, 30))


# ---------- screen labels in any language (Sarvam, cached for everyone) ----------
@app.post("/api/ui-translate")
def ui_translate():
    b = body()
    language = b.get("language", "en")
    texts = [str(t)[:200] for t in (b.get("texts") or [])][:120]
    if language == "en" or not texts:
        return ok({"texts": texts})
    if language not in agent.LANG_NAMES:
        raise ValueError("Unknown language")
    key = f"ui:{language}"
    cache = store.meta_get(key) or {}
    missing = [t for t in dict.fromkeys(texts) if t not in cache]
    engine = "cache"
    if missing:
        r = agent.translate(missing, language)
        if not r.get("note"):
            cache.update(dict(zip(missing, r["texts"])))
            store.meta_set(key, cache)
            engine = r.get("engine", "")
    return ok({"texts": [cache.get(t, t) for t in texts], "engine": engine})


# ---------- for engineers: what is running, and every endpoint ----------
START = time.time()


@app.get("/api/system")
def system():
    import platform
    import flask
    from ustaad import ocr
    tests = sorted(p.name for p in (BASE / "tests").glob("test_*.py")) if (BASE / "tests").exists() else []
    return ok({
        "status": status().get_json(),
        "models": {"answers_written_by": " → ".join(f"{n} ({m})" for n, m in llm.writers()) or "rules (no AI key)",
                   "speech_to_text": config.SARVAM_STT_MODEL,
                   "backup_ears": "Google speech, then Groq " + config.GROQ_WHISPER_MODEL, "translation": config.SARVAM_TRANSLATE_MODEL,
                   "voice_out": config.SARVAM_TTS_MODEL, "ocr": "Sarvam Vision (Document Intelligence)" if ocr.available() else "Groq vision (backup)",
                   "vision_backup": getattr(config, "GROQ_VISION_MODEL", "Groq vision")},
        "voice": voice.status(), "ocr": ocr.available(),
        "runtime": {"python": platform.python_version(), "flask": flask.__version__, "uptime_minutes": round((time.time() - START) / 60),
                    "commit": (os.getenv("RENDER_GIT_COMMIT") or "")[:7], "server": "gunicorn on Render (512 MB)" if os.getenv("RENDER") else "local"},
        "data": {i: {"records": len(store.records(i)), "machines": len(packs.assets(i)), "bank": config.bank_id(i)} for i in packs.ids()},
        "tests": tests})


@app.get("/api/endpoints")
def endpoints():
    out = []
    for r in app.url_map.iter_rules():
        if not r.rule.startswith("/api/"):
            continue
        fn = app.view_functions.get(r.endpoint)
        doc = ((fn.__doc__ or "").strip().split("\n")[0]) if fn else ""
        out.append({"path": r.rule, "methods": sorted(m for m in r.methods if m in ("GET", "POST", "DELETE", "PUT")), "doc": doc})
    return ok({"endpoints": sorted(out, key=lambda x: x["path"])})


# ---------- installable app (PWA) ----------
@app.get("/manifest.webmanifest")
def manifest():
    return app.response_class(json.dumps({
        "name": "Ustaad — the expert who never leaves", "short_name": "Ustaad", "start_url": "/", "display": "standalone",
        "background_color": "#fbf8f3", "theme_color": "#16202e", "description": "Your team's proven fixes, by voice, in your language.",
        "icons": [{"src": "/static/icons/icon-192.png", "sizes": "192x192", "type": "image/png"},
                  {"src": "/static/icons/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"}]}),
        mimetype="application/manifest+json")


@app.get("/sw.js")
def service_worker():
    resp = send_from_directory("static", "sw.js")
    resp.headers["Service-Worker-Allowed"] = "/"
    resp.headers["Cache-Control"] = "no-cache"
    return resp


# ---------- Stage 4: capture know-how and people ----------
@app.post("/api/i/<industry>/logbook/read")
def logbook_read(industry):
    f = request.files.get("image")
    if not f:
        raise ValueError("Take a photo of the logbook page")
    return ok(knowhow.logbook_read(_ind(industry), f.read(), f.mimetype or "image/jpeg", request.form.get("language")))


@app.post("/api/i/<industry>/logbook/save")
def logbook_save(industry):
    b = body()
    return ok(knowhow.logbook_save(_ind(industry), b.get("entries"), b.get("person_id"), b.get("page_ref", "")))


@app.post("/api/i/<industry>/video-guide")
def video_guide(industry):
    """A phone video of a fix -> a step-by-step guide (the phone sends the sound as WAV and a few frames)."""
    frames = []
    for f in request.files.getlist("frames"):
        try:
            frames.append((float(f.filename.rsplit("_", 1)[-1].split(".")[0]), f.read()))
        except ValueError:
            continue
    a, v = request.files.get("audio"), request.files.get("video")
    return ok(knowhow.video_guide(_ind(industry), request.form.get("asset_id"), request.form.get("person_id"),
                                  wav=a.read() if a else None, frames=frames, video=v.read() if v else None,
                                  video_name=v.filename if v else "video.mp4", language=request.form.get("language")))


@app.post("/api/i/<industry>/guides")
def guide_save(industry):
    b = body()
    return ok(knowhow.save_guide(_ind(industry), b.get("guide") or {}, b.get("person_id")))


@app.get("/api/i/<industry>/guides")
def guides_list(industry):
    return ok({"guides": knowhow.guides(_ind(industry), request.args.get("asset_id"))})


@app.get("/api/i/<industry>/guides/<gid>")
def guide_get(industry, gid):
    return ok(knowhow.guide(_ind(industry), gid))


@app.get("/api/i/<industry>/machines/<asset_id>/quiz")
def machine_quiz(industry, asset_id):
    return ok(knowhow.manual_quiz(_ind(industry), asset_id, seed=request.args.get("seed")))


@app.get("/api/i/<industry>/experts")
def experts_find(industry):
    """Who can fix this? People ranked by proof (fixes that worked), not job title."""
    return ok(knowhow.find_experts(_ind(industry), request.args.get("q", "")))


# ---------- Stage 5: daily use and AI access ----------
@app.get("/api/i/<industry>/briefing")
def briefing(industry):
    """Today's morning briefing in plain sentences (and in the chosen language)."""
    return ok(daily.briefing(_ind(industry), request.args.get("site") or None, request.args.get("language", "en")))


@app.get("/machines/<industry>/<asset_id>.md")
def machine_md(industry, asset_id):
    """One machine as a Markdown file — readable by people and by other AIs."""
    return app.response_class(daily.machine_markdown(_ind(industry), asset_id), mimetype="text/markdown")


@app.get("/llms.txt")
def llms_txt():
    return app.response_class(daily.llms_txt(request.host_url.rstrip("/")), mimetype="text/plain")


@app.route("/mcp", methods=["POST", "GET", "DELETE"])
def mcp():
    """MCP server (Streamable HTTP, JSON-RPC 2.0): any AI assistant can ask the plant's memory."""
    if request.method != "POST":
        return app.response_class(status=405, headers={"Allow": "POST"})
    if not mcp_server.authorized(request.headers):
        return jsonify({"jsonrpc": "2.0", "id": None, "error": {"code": -32001, "message": "Unauthorized"}}), 401
    msg = request.get_json(silent=True)
    if msg is None:
        return jsonify({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}), 400
    if isinstance(msg, list):
        out = [r for r in (mcp_server.handle(m) for m in msg) if r is not None]
        return (jsonify(out), 200) if out else app.response_class(status=202)
    r = mcp_server.handle(msg)
    return jsonify(r) if r is not None else app.response_class(status=202)


@app.get("/api/benchmark")
def bench_get():
    return ok(benchmark.overview())


@app.post("/api/benchmark/run")
def bench_run():
    started = benchmark.run_web(body().get("case"))
    return ok({"started": started, **benchmark.overview()})


@app.post("/api/benchmark/file")
def bench_file():
    f = request.files.get("file")
    if not f:
        raise ValueError("Upload the PDF")
    return ok(benchmark.run_file(f.read()))


@app.post("/api/i/<industry>/machines/<asset_id>/stock")
def machine_stock(industry, asset_id):
    b = body()
    return ok(machines.set_stock(_ind(industry), asset_id, b.get("part"), b.get("stock")))


@app.post("/api/i/<industry>/sensors/alert")
def sensor_alert(industry):
    b = body()
    return ok(machines.sensor_alert(_ind(industry), b.get("asset_id"), b.get("reading") or {}))


@app.get("/api/i/<industry>/alerts")
def alerts(industry):
    """🏭 The machine calls first: machines whose sensor crossed its limit and are waiting for someone."""
    return ok({"alerts": machines.open_alerts(_ind(industry))})


@app.get("/api/i/<industry>/network")
def network_lookup(industry):
    """🌐 What worked in other plants for this problem (names hidden; sample data in the demo)."""
    ind = _ind(industry)
    a = packs.asset(ind, request.args.get("asset_id"))
    if not a:
        raise ValueError("Unknown item")
    return ok({"other_plants": network.lookup(ind, a, request.args.get("problem", "")), **network.settings(ind)})


@app.route("/api/i/<industry>/network/settings", methods=["GET", "POST"])
def network_settings(industry):
    ind = _ind(industry)
    if request.method == "POST":
        out = network.set_share(ind, bool(body().get("share")))
        backup.mark_dirty()
        return ok(out)
    return ok(network.settings(ind))


@app.post("/api/i/<industry>/sensors/reading")
def sensor_reading(industry):
    """For a real sensor gateway: {"asset_id": "CNC-3", "vib": 2.1, "temp": 41, "hours": 12850}  (hours = hour meter, optional)"""
    b = body()
    return ok(machines.sensor_reading(_ind(industry), b.get("asset_id"), b.get("vib", 0), b.get("temp", 0), b.get("hours")))


# ---------- one-time Hindsight seeding from the deployed app (protected by SEED_TOKEN) ----------
SEED = {"running": False, "log": []}


@app.route("/api/admin/seed", methods=["GET", "POST"])
def admin_seed():
    token = os.getenv("SEED_TOKEN", "")
    if not token or request.args.get("token") != token:
        return err("Set SEED_TOKEN in Render and open /api/admin/seed?token=<your token>", 403)
    if not memory.cloud:
        return err("HINDSIGHT_API_KEY is not set on the server", 400)
    if SEED["running"]:
        return ok({"running": True, "log": SEED["log"][-20:]})
    import threading
    from ustaad.memory import all_memories
    only = request.args.get("industry")

    def _run():
        SEED.update(running=True, log=[])
        for ind in ([only] if only else packs.ids()):
            try:
                memory.cloud.setup_bank(ind)
                SEED["log"].append(f"{ind}: bank created")
            except Exception as e:
                SEED["log"].append(f"{ind}: bank — {str(e)[:100]}")
            mems = all_memories(ind)
            for i in range(0, len(mems), 25):
                try:
                    memory.cloud.retain_batch(ind, mems[i:i + 25])
                    SEED["log"].append(f"{ind}: saved {min(i + 25, len(mems))}/{len(mems)}")
                except Exception as e:
                    SEED["log"].append(f"{ind}: FAILED at {i} — {str(e)[:150]}")
        SEED["log"].append("DONE")
        SEED["running"] = False
    if config.ON_VERCEL or request.args.get("sync") == "1":  # serverless: finish inside this request
        _run()
        return ok({"done": True, "log": SEED["log"]})
    threading.Thread(target=_run, daemon=True).start()
    return ok({"started": True, "message": "Seeding started. Refresh this page to see progress."})


# ---------- factory extras ----------
@app.get("/api/factory/sensors")
def sensors():
    return ok(packs.processed("factory_sensors.json") | {"alerts": agent.sensor_alerts()})


@app.get("/api/factory/fleet")
def fleet():
    return ok(packs.processed("factory_fleet.json"))


@app.get("/api/factory/ai4i")
def ai4i():
    return ok(packs.processed("factory_ai4i.json"))


logs.startup()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=False)
