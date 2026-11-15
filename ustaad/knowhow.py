"""
Capturing know-how and people (Stage 4):
  logbook_read / logbook_save   a photo of an old handwritten register -> one memory per entry (a senior approves)
  video_guide / save_guide      a phone video of a fix -> a step-by-step guide with a photo per step
  person_cards                  "Ask Ramesh": only that person's own fixes
  manual_quiz                   5 questions from a machine's own manual (or its checked specs), with the page
  find_experts                  "who can fix hydraulic leaks at Pune?" -> people ranked by proof, not job title
  passport_extra                evidence for every skill, a skill graph, privacy mode
"""
import base64
import io
import json
import random
import re
import subprocess
import tempfile
import uuid
import wave
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from . import lang, llm, ocr, packs, store, voice
from .memory import _tokens

DATE = re.compile(r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})\b|\b(\d{4})-(\d{2})-(\d{2})\b")
STOP = {"who", "can", "fix", "fixes", "repair", "the", "a", "an", "at", "in", "on", "for", "of", "and", "is", "best", "good",
        "kaun", "ko", "ka", "ki", "me", "mein", "hai", "expert", "someone", "person", "which", "knows", "know"}


def _people_match(industry, name):
    """'Ramesh' / 'R. Gowda' / 'रमेश' -> the person in this team, or None."""
    n = (name or "").strip().lower()
    if not n:
        return None
    for p in packs.people(industry):
        full = p["name"].lower()
        first = full.split()[0]
        if n == full or n == first or first in n.split() or (len(n) > 3 and n in full):
            return p
    return None


def _asset_in(industry, text):
    for a in sorted(packs.assets(industry), key=lambda a: -len(a["id"])):
        parts = [x for x in re.split(r"[-_\s]+", a["id"]) if x]
        pat = r"(?<![\w-])" + r"\s*[-‐–]?\s*".join(map(re.escape, parts)) + r"(?![\w-])"
        if re.search(pat, text or "", re.I):
            return a["id"]
    return None


# ---------- 📓 old logbook pages ----------
def logbook_read(industry, image_bytes, mime="image/jpeg", language=None):
    code = lang.SARVAM_CODE.get(language) if language and language != "en" else "en-IN"
    text, by = None, None
    if ocr.available():
        text = ocr.image_text(image_bytes, mime, code)
        by = "Sarvam Vision"
    if not text and llm.groq_available():
        data = llm.vision_json("This is a page of a handwritten maintenance register. Copy every line exactly as written, "
                               "keeping dates, machine names and numbers. Return ONLY JSON: {\"text\": \"all lines, one per line\"}",
                               base64.b64encode(image_bytes).decode(), mime, 1500)
        text = (data or {}).get("text") if isinstance(data, dict) else None
        by = "Groq vision (backup)"
    if not text:
        raise ValueError("Couldn't read the page. Take the photo flat, in good light, with the whole page inside.")
    english, _ = lang.to_english(text)
    entries = None
    if llm.available():
        listing = "\n".join(f"- {a['id']}: {a['name']}" for a in packs.assets(industry))
        people = ", ".join(p["name"] for p in packs.people(industry))
        data = llm.chat_json(
            "These lines come from a photo of an old handwritten maintenance register (read by OCR, so expect spelling errors). "
            "Split it into one entry per job. Pick asset_id ONLY from the list (empty if unsure). Use simple English. "
            "outcome is fixed, failed_again, temporary or open. Never invent anything that isn't written. Return ONLY JSON: "
            '{"entries": [{"date": "YYYY-MM-DD or empty", "asset_id": "", "problem": "", "cause": "", "action": "", '
            '"outcome": "fixed", "person": "name as written", "minutes": 0, "line": "the original line(s)"}]}',
            f"MACHINES:\n{listing}\nPEOPLE: {people}\n\nREGISTER PAGE:\n{english[:6000]}", 3000)
        if isinstance(data, dict) and isinstance(data.get("entries"), list):
            entries = [e for e in data["entries"] if isinstance(e, dict) and (e.get("problem") or e.get("action"))]
    if entries is None:  # no AI: one entry per dated line
        entries = []
        for line in english.split("\n"):
            line = line.strip(" -•|")
            if len(line) < 8:
                continue
            m = DATE.search(line)
            if not m and entries:
                entries[-1]["action"] = (entries[-1]["action"] + " " + line).strip()
                entries[-1]["line"] += "\n" + line
                continue
            who = next((pp["name"] for pp in packs.people(industry)
                        if re.search(r"\b" + re.escape(pp["name"].split()[0]) + r"\b", line, re.I)), "")
            entries.append({"date": "", "asset_id": "", "problem": DATE.sub("", line).strip(" -:")[:120], "cause": "",
                            "action": "", "outcome": "fixed" if re.search(r"\b(ok|done|fixed|theek|sahi)\b", line, re.I) else "open",
                            "person": who, "minutes": 0, "line": line})
    out = []
    for e in entries[:40]:
        aid = e.get("asset_id") if packs.asset(industry, e.get("asset_id")) else _asset_in(industry, e.get("line", "") + " " + e.get("problem", ""))
        p = _people_match(industry, e.get("person"))
        d = str(e.get("date") or "")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", d):
            m = DATE.search(e.get("line", "") + " " + d)
            d = ""
            if m and m.group(1):
                y = int(m.group(3)) + (2000 if len(m.group(3)) == 2 else 0)
                try:
                    d = datetime(y, int(m.group(2)), int(m.group(1))).date().isoformat()
                except ValueError:
                    d = ""
            elif m:
                d = f"{m.group(4)}-{m.group(5)}-{m.group(6)}"
        out.append({"date": d, "asset_id": aid or "", "problem": str(e.get("problem") or "")[:160], "cause": str(e.get("cause") or "")[:200],
                    "action": str(e.get("action") or "")[:300], "outcome": e.get("outcome") if e.get("outcome") in ("fixed", "failed_again", "temporary", "open") else "open",
                    "person_id": p["id"] if p else "", "person_written": str(e.get("person") or "")[:40],
                    "minutes": float(e.get("minutes") or 0), "line": str(e.get("line") or "")[:400]})
    return {"text": text[:4000], "read_by": by, "entries": out, "written_by": llm.last_provider if llm.available() else "rules (no AI key)"}


def logbook_save(industry, entries, scanned_by, page_ref=""):
    """Each checked entry becomes a record (status: waiting for a senior's approval) and a memory."""
    from .memory import memory, record_to_memory
    saved = []
    for e in entries or []:
        if not (isinstance(e, dict) and packs.asset(industry, e.get("asset_id")) and (e.get("problem") or e.get("action"))):
            continue
        when = (e.get("date") or "")[:10]
        rec = store.add_record(industry, {
            "datetime": f"{when}T09:00" if re.fullmatch(r"\d{4}-\d{2}-\d{2}", when) else None,
            "asset_id": e["asset_id"], "person_id": e.get("person_id") or scanned_by or "",
            "problem": e.get("problem") or e.get("action")[:80], "cause": e.get("cause", ""), "action": e.get("action", ""),
            "outcome": e.get("outcome") or "open", "downtime_minutes": e.get("minutes") or 0, "status": "pending", "source": "logbook",
            "source_ref": page_ref or "Scanned logbook page",
            "notes": f"From an old logbook page (written by {e.get('person_written') or 'unknown'}): {e.get('line', '')[:300]}"})
        memory.retain(industry, record_to_memory(industry, rec))
        saved.append(rec["id"])
    return {"saved": len(saved), "ids": saved,
            "message": f"✔ {len(saved)} entries saved from the logbook. They show as 'Not checked yet' until a senior approves them."}


# ---------- 🎥 fix video -> step-by-step guide ----------
def _wav_chunks(wav_bytes, seconds=25):
    with wave.open(io.BytesIO(wav_bytes)) as w:
        rate, width, ch, n = w.getframerate(), w.getsampwidth(), w.getnchannels(), w.getnframes()
        step = rate * seconds
        for start in range(0, n, step):
            w.setpos(start)
            frames = w.readframes(min(step, n - start))
            buf = io.BytesIO()
            with wave.open(buf, "wb") as o:
                o.setnchannels(ch)
                o.setsampwidth(width)
                o.setframerate(rate)
                o.writeframes(frames)
            yield start / rate, buf.getvalue()


def _from_video(video_bytes, name):
    """Server-side backup when the phone couldn't split the video itself: audio (WAV) + up to 8 frames."""
    exe = voice.ffmpeg()
    if not exe:
        raise ValueError("This server can't read videos (ffmpeg missing)")
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / ("in" + (Path(name).suffix or ".mp4"))
        src.write_bytes(video_bytes)
        subprocess.run([exe, "-loglevel", "error", "-y", "-i", str(src), "-t", "180", "-ac", "1", "-ar", "16000", "-vn", str(Path(d) / "a.wav")],
                       capture_output=True, timeout=90)
        subprocess.run([exe, "-loglevel", "error", "-y", "-i", str(src), "-t", "180", "-vf", "fps=1/8,scale=480:-2", "-q:v", "6",
                        str(Path(d) / "f%02d.jpg")], capture_output=True, timeout=90)
        wav = (Path(d) / "a.wav").read_bytes() if (Path(d) / "a.wav").exists() else None
        frames = [((int(f.stem[1:]) - 1) * 8 + 4, f.read_bytes()) for f in sorted(Path(d).glob("f*.jpg"))][:8]
    return wav, frames


def video_guide(industry, asset_id, person_id, wav=None, frames=None, video=None, video_name="video.mp4", language=None):
    a = packs.asset(industry, asset_id)
    if not a:
        raise ValueError("Pick the machine this video is about")
    if video and not wav:
        wav, frames = _from_video(video, video_name)
    if not wav:
        raise ValueError("No sound found in the video — explain what you're doing while you record")
    parts = []
    for start, chunk in _wav_chunks(wav):
        r = voice.transcribe(chunk, "chunk.wav", "audio/wav", language, industry)
        if r["text"]:
            parts.append({"at": round(start), "text": r["text"], "by": r["engine"]})
    if not parts:
        raise ValueError("Couldn't hear any words in the video. Speak clearly while you show each step.")
    english = []
    for p in parts:
        en, _ = lang.to_english(p["text"])
        english.append({"at": p["at"], "text": en})
    transcript = "\n".join(f"[{p['at']}s] {p['text']}" for p in english)
    guide = None
    if llm.available():
        who = (packs.person(industry, person_id) or {}).get("name", "a technician")
        data = llm.chat_json(
            f"{who} recorded a phone video while fixing {a['id']} ({a.get('name', '')}) and explained it out loud. Below is what they "
            "said, with the second it was said. Turn it into a short step-by-step guide another worker can follow. Keep their own "
            "words, numbers and values; never add steps they didn't do. Return ONLY JSON: {\"title\": \"\", \"summary\": \"1 sentence\", "
            "\"steps\": [{\"text\": \"one action\", \"at\": 0}], \"tools\": [\"\"], \"safety\": \"\"}",
            transcript[:6000], 1600)
        if isinstance(data, dict) and data.get("steps"):
            guide = data
    if not guide:  # no AI: each spoken part is a step
        guide = {"title": f"How {a['id']} was fixed", "summary": "", "tools": [], "safety": "",
                 "steps": [{"text": p["text"], "at": p["at"]} for p in english]}
    frames = sorted(frames or [], key=lambda f: f[0])

    def frame_for(t):
        best = None
        for ft, img in frames:
            if ft <= (t or 0) + 6:
                best = img
        return best or (frames[0][1] if frames else None)
    steps = []
    for s in guide.get("steps") or []:
        if not isinstance(s, dict) or not s.get("text"):
            continue
        try:
            t = float(s.get("at") or 0)
        except (TypeError, ValueError):
            t = 0
        img = frame_for(t)
        steps.append({"text": str(s["text"])[:300], "at": round(t),
                      "image": "data:image/jpeg;base64," + base64.b64encode(img).decode() if img else None})
    return {"draft_id": uuid.uuid4().hex[:8], "asset_id": a["id"], "person_id": person_id, "title": str(guide.get("title") or "")[:100],
            "summary": str(guide.get("summary") or "")[:300], "tools": [str(x) for x in guide.get("tools") or [] if x][:8],
            "safety": str(guide.get("safety") or "")[:300], "steps": steps[:15], "transcript": transcript[:4000],
            "heard_by": ", ".join(sorted({p["by"] for p in parts})), "written_by": llm.last_provider if llm.available() else "rules (no AI key)"}


def save_guide(industry, g, person_id):
    from . import agent
    if not packs.asset(industry, g.get("asset_id")) or not g.get("steps"):
        raise ValueError("Nothing to save")
    gid = "vg-" + uuid.uuid4().hex[:8]
    steps = [{"text": str(s.get("text", ""))[:300], "at": s.get("at", 0),
              "image": s.get("image") if str(s.get("image") or "").startswith("data:image/jpeg;base64,") and len(s.get("image") or "") < 120_000 else None}
             for s in g["steps"][:15]]
    doc = {"id": gid, "asset_id": g["asset_id"], "person_id": person_id or g.get("person_id") or "", "title": str(g.get("title") or "Video guide")[:100],
           "summary": str(g.get("summary") or "")[:300], "tools": g.get("tools") or [], "safety": str(g.get("safety") or "")[:300],
           "steps": steps, "created": datetime.now().isoformat(timespec="minutes")}
    store.meta_set(f"guide:{industry}:{gid}", doc)
    idx = store.meta_get(f"guides:{industry}") or {}
    idx[gid] = {"asset_id": doc["asset_id"], "title": doc["title"], "person_id": doc["person_id"], "created": doc["created"], "steps": len(steps)}
    store.meta_set(f"guides:{industry}", idx)
    text = f"Video guide '{doc['title']}' for {doc['asset_id']}: " + " ".join(f"{i}. {s['text']}" for i, s in enumerate(steps, 1))
    tip = None
    if packs.person(industry, doc["person_id"]):
        tip = agent.add_tip(industry, doc["person_id"], doc["asset_id"], text[:1500], f"video guide {gid}")
    return {"guide": {k: v for k, v in doc.items() if k != "steps"} | {"steps": len(steps)}, "id": gid, "memory": bool(tip),
            "message": "✔ Guide saved. Its steps are in memory too, so answers can point to it."}


def guides(industry, asset_id=None):
    idx = store.meta_get(f"guides:{industry}") or {}
    rows = [{"id": k, **v} for k, v in idx.items() if not asset_id or v.get("asset_id") == asset_id]
    for r in rows:
        r["person"] = (packs.person(industry, r.get("person_id")) or {}).get("name", "")
    return sorted(rows, key=lambda r: r.get("created", ""), reverse=True)


def guide(industry, gid):
    g = store.meta_get(f"guide:{industry}:{gid}")
    if not g:
        raise ValueError("Unknown guide")
    g["person"] = (packs.person(industry, g.get("person_id")) or {}).get("name", "")
    return g


# ---------- 🧓 ask one expert ----------
def person_cards(industry, person_id, problem, cards, asset):
    """Keep only memories from this person; add their own matching records if search missed them."""
    from .agent import memory_card
    mine = [c for c in cards if c.get("person_id") == person_id]
    seen = {c["key"] for c in mine}
    q = set(_tokens(problem))
    codes = set(re.findall(r"\b\d{3,5}\b", problem or ""))
    extra = []
    for r in store.records(industry):
        if r["person_id"] != person_id or r["status"] == "rejected" or r["id"] in seen:
            continue
        blob = set(_tokens(" ".join([r["problem"], r.get("symptom") or "", r.get("cause") or "", r.get("action") or ""])))
        score = len(q & blob) + (3 if codes and str(r.get("code") or "") in codes else 0) + (1 if asset and r["asset_id"] == asset.get("id") else 0)
        if score >= 2:
            extra.append((score, r))
    extra.sort(key=lambda x: -x[0])
    for i, (_, r) in enumerate(extra[:6]):
        mine.append(memory_card(industry, {"key": r["id"], "kind": "record", "text": f"{r['problem']}: {r['action']}"}, f"M{len(cards) + i + 1}", asset))
    return mine


# ---------- 🎓 quiz from a machine's own manual ----------
def manual_quiz(industry, aid, n=5, seed=None):
    from .expert import _quote_on_page
    from . import specs as spec
    a = packs.asset(industry, aid)
    if not a:
        raise ValueError("Unknown item")
    rnd = random.Random(seed or datetime.now().strftime("%Y%m%d%H"))
    pages = [p for p in store.manual_pages(industry, aid) if p.get("kept")] or store.manual_pages(industry, aid)
    qs = []
    if pages and llm.available():
        by_page = {p["page"]: p["text"] for p in pages}
        ctx = "\n\n".join(f"[page {p['page']}]\n{p['text'][:1800]}" for p in pages[:6])[:9000]
        data = llm.chat_json(
            f"Write {n} multiple-choice questions that check a new technician really read the maker's manual for {a['id']} "
            "({a.get('name', '')}): limits, settings, safety, maintenance intervals, what an alarm means. Use ONLY these pages. "
            "Each question: 4 short options, one right. Give the page and an EXACT quote (5-20 words) that proves the answer. "
            'Return ONLY JSON: {"questions": [{"question": "", "options": ["", "", "", ""], "answer": 0, "page": 0, "quote": "", "explain": ""}]}',
            ctx, 2200)
        for q in (data.get("questions") or []) if isinstance(data, dict) else []:
            try:
                opts = [str(o) for o in q["options"]][:4]
                ans = int(q["answer"])
                if len(opts) < 3 or not 0 <= ans < len(opts):
                    continue
            except (KeyError, TypeError, ValueError):
                continue
            page = q.get("page")
            ok = bool(q.get("quote") and page in by_page and _quote_on_page(q["quote"], by_page[page]))
            qs.append({"question": str(q.get("question", ""))[:300], "options": opts, "answer": ans, "page": page if ok else None,
                       "checked": ok, "explain": (f"Manual p.{page}: “{q['quote']}”" if ok else str(q.get("explain") or ""))[:300]})
        qs.sort(key=lambda q: not q["checked"])
    if len(qs) < n:  # no AI (or too few): questions from the machine's checked specs and service intervals
        fields = [f for f in a.get("spec_fields") or [] if f.get("value") and f.get("status") in ("verified", "converted")]
        others = defaultdict(list)
        for x in packs.assets(industry):
            for f in x.get("spec_fields") or []:
                if f.get("value") and x["id"] != aid:
                    others[f["key"]].append(spec.show(f))
        for f in fields:
            right = spec.show(f)
            right = re.sub(r"\s*\(from [^)]*\)", "", right).strip()  # '15.5 kW (from 53,000 BTU)' -> '15.5 kW'
            wrong = [re.sub(r"\s*\(from [^)]*\)", "", w).strip() for w in dict.fromkeys(others[f["key"]])]
            nums = re.findall(r"\d+(?:\.\d+)?", right)
            if len(nums) == 1:  # same look as the right answer, only the number changes
                v = float(nums[0])
                wrong += [right.replace(nums[0], f"{round(v * k, 2):g}", 1) for k in (0.5, 1.5, 2)]
            wrong = [w for w in dict.fromkeys(wrong) if w and w != right][:3]
            if len(wrong) < 2:
                continue
            opts = wrong + [right]
            rnd.shuffle(opts)
            pg = re.search(r"page (\d+)", f.get("where") or "")
            qs.append({"question": f"{f['label']} of {a['id']} — which is right?", "options": opts, "answer": opts.index(right),
                       "page": int(pg.group(1)) if pg else None, "checked": True, "explain": f"From the maker's documents: “{f.get('quote') or f['value']}”."})
        for c in a.get("components") or []:
            if c.get("every_days"):
                right = f"every {c['every_days']} days"
                opts = list(dict.fromkeys([right, f"every {c['every_days'] * 2} days", f"every {max(7, c['every_days'] // 2)} days", "only when it breaks"]))
                rnd.shuffle(opts)
                qs.append({"question": f"How often should the {c['name'].lower()} on {a['id']} be replaced?", "options": opts,
                           "answer": opts.index(right), "page": None, "checked": True, "explain": f"The service plan says {right}."})
    if not qs:
        raise ValueError(f"No manual or checked specs stored for {aid} yet — add its manual first.")
    return {"asset": {"id": aid, "name": a.get("name")}, "questions": qs[:n], "from": "manual pages" if pages and llm.available() else "checked specs"}


# ---------- 🔎 expert finder ----------
def find_experts(industry, query):
    q = (query or "").strip()
    if len(q) < 3:
        raise ValueError("Type what needs fixing, e.g. hydraulic leak at Pune")
    en, _ = lang.to_english(q)
    pk = packs.get(industry)
    site = next((s for s in pk.get("sites", []) if any(w.lower() in en.lower() for w in re.findall(r"[A-Za-z]{4,}", s["name"]))), None)
    words = {w for w in _tokens(en) if w not in STOP}
    if site:
        words -= set(_tokens(site["name"]))
    codes = set(re.findall(r"\b\d{3,5}\b", en))
    score, proof = defaultdict(float), defaultdict(list)
    recs = [r for r in store.records(industry) if r["status"] != "rejected" and r["outcome"] == "fixed"]
    for r in recs:
        a = packs.asset(industry, r["asset_id"]) or {}
        if site and a.get("site") != site["id"]:
            continue
        blob = set(_tokens(" ".join([r["problem"], r.get("symptom") or "", r.get("cause") or "", r.get("action") or "", a.get("name", ""), a.get("type", "")])))
        hit = len(words & blob) + (3 if codes and str(r.get("code") or "") in codes else 0)
        if hit == 0:
            continue
        for pid, w in ((r["person_id"], 1.0), (r.get("credited_to"), 0.6)):  # the fixer, and whose fix was reused
            if pid and packs.person(industry, pid):
                score[pid] += w * hit
                if w == 1.0:
                    proof[pid].append({"date": r["datetime"][:10], "asset_id": r["asset_id"], "problem": r["problem"], "action": r["action"][:120]})
    out = []
    for pid, sc in sorted(score.items(), key=lambda x: -x[1])[:5]:
        p = packs.person(industry, pid)
        ev = sorted(proof[pid], key=lambda x: x["date"], reverse=True)
        out.append({"id": pid, "name": p["name"], "role": p.get("role"), "site": (packs.site(industry, p.get("site")) or {}).get("name", ""),
                    "score": round(sc, 1), "fixes": len(ev), "proof": ev[:3], "leaving": p.get("retiring_on"),
                    "message": f"Hi {p['name'].split()[0]}, can you help? {q} — Ustaad says you've fixed this {len(ev)} time(s)."})
    return {"query": q, "site": site["name"] if site else None, "words": sorted(words)[:8], "experts": out}


# ---------- 🏅 passport: evidence, graph, privacy ----------
def passport_extra(industry, person_id, data, private=False):
    """Adds the proof behind every skill (which fixes, who confirmed) and a privacy mode for sharing."""
    recs = [r for r in store.records(industry) if r["status"] != "rejected"]
    for s in data["skills"]:
        ev = []
        for r in recs:
            if r["problem"] == s["skill"] and r["outcome"] == "fixed" and (r["person_id"] == person_id or r.get("credited_to") == person_id):
                by_other = r["person_id"] != person_id
                approver = (packs.person(industry, r.get("approved_by")) or {}).get("name") if r.get("approved_by") and r.get("approved_by") != person_id else None
                ev.append({"date": r["datetime"][:10], "asset_id": r["asset_id"], "action": r["action"][:140],
                           "kind": "reused by " + (packs.person(industry, r["person_id"]) or {}).get("name", "a colleague") if by_other else "own fix",
                           "approved_by": approver})
        s["evidence"] = sorted(ev, key=lambda x: x["date"], reverse=True)[:6]
        s["independent"] = len({(e["date"], e["kind"]) for e in ev}) + sum(1 for e in ev if e["approved_by"])
    if private:
        parts = data["person"]["name"].split()
        data["person"] = {**data["person"], "name": parts[0] + (f" {parts[-1][0]}." if len(parts) > 1 else ""), "phone": None}
        data["org"] = "Private (company hidden)"
        data["private"] = True
    return data
