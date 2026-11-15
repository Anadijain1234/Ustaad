/* Ustaad frontend — plain JavaScript, no build step. */
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const app = $("#app");
const S = { status: null, industries: null, packs: {}, ind: null, role: null, person: null, lang: "en", prefill: null, charts: [] };

const TOOLS = {
  ask: ["💬", "Ask Ustaad"], log: ["✍️", "I fixed something"], memory: ["🧠", "Memory"], approvals: ["✅", "Approvals"],
  playbook: ["📋", "SOP / playbook"], risk: ["⚠️", "Risk radar"], interview: ["🎤", "Exit interview"], shift: ["🔁", "Shift report"],
  skills: ["🧩", "Skill map"], passport: ["🏅", "Skill passport"], stats: ["📈", "ROI dashboard"], quiz: ["🎓", "Learn (quiz)"],
  sensors: ["📡", "Live sensors"], fleet: ["🔮", "Failure prediction"], check: ["🧮", "Failure check"], dishes: ["🍽️", "Customer & hygiene data"],
  checklist: ["✔️", "OT checklist"], devices: ["🩺", "Device reports"], obd: ["🔧", "OBD codes"], outages: ["🌐", "Outage library"],
  machines: ["🏭", "My machines"], coverage: ["🗺️", "Knowledge coverage"], leaderboard: ["🏆", "Expert leaderboard"],
};
// one plain line on top of every screen: what is this?
const HELP = {
  ask: "Describe a problem. Ustaad finds what your team did before, who did it and whether it worked.",
  log: "Just fixed something? Say it in any language. It becomes a memory for the next person.",
  machines: "Every machine in one place: details, health, service due, spare parts, fix history, who knows it best — and a QR sticker.",
  memory: "Everything Ustaad remembers, with how much to trust each memory.",
  approvals: "New knowledge waits here until a senior checks it.",
  playbook: "One printable standard procedure, built only from fixes that actually worked.",
  risk: "Which know-how leaves the building if a senior person leaves.",
  interview: "Questions for a leaving expert — only about things nobody has written down yet.",
  shift: "A handover note built from real records, sensor alerts and low spare parts.",
  skills: "Who has proven fixes on which machine.",
  passport: "Proof of a person's skills, built from fixes that worked.",
  stats: "ROI dashboard: downtime hours saved, repeat failures avoided, fixed vs failed, ₹ saved — before vs after Ustaad.",
  coverage: "How much of each machine's know-how is captured, and where only one person knows it.",
  leaderboard: "Who shares knowledge that others actually use. Points for fixes that worked and fixes others reused.",
  quiz: "New joiners learn from this team's own past problems.",
  sensors: "Sensors say something is wrong. Ustaad logs it by itself and shows what fixed it last time.",
  fleet: "A model trained on public data guesses which machine may fail next.",
  check: "Enter machine settings — rules from 10,000 public runs say what may fail.",
  dishes: "Real customer-complaint and hygiene data behind the kitchen memories.",
  checklist: "The WHO surgical safety checklist plus this hospital's own additions.",
  devices: "Real FDA reports about ventilators and pumps.",
  obd: "What a car's error code means, plus what our mechanics found.",
  outages: "240 real public outage write-ups next to the team's own incidents.",
};
const GROUPS = [["Daily work", ["ask", "log", "machines"]], ["Team knowledge", ["memory", "approvals", "playbook", "quiz", "interview", "leaderboard"]],
  ["For managers", ["stats", "coverage", "risk", "shift", "skills", "passport"]]];
const OUTCOME = { fixed: "Worked", failed_again: "Didn't work", temporary: "Temporary", open: "Still open" };
const TIER = { verified: ["b-verified", "✔ Worked many times"], tested: ["b-tested", "✔ Worked once"], unreviewed: ["b-unreviewed", "Not checked yet"],
  failed: ["b-failed", "✖ Didn't work"], public: ["b-public", "Public record"], attested: ["b-attested", "Attested"], self: ["b-self", "Self-declared"],
  manual: ["b-manual", "📘 Maker's manual"], insight: ["b-insight", "🧠 Pattern Ustaad noticed"], hfact: ["b-insight", "🧠 Remembered fact"], sensor: ["b-verified", "📡 Confirmed by the sensor"] };
const toolName = (t) => (t === "machines" && S.ind && pack() ? `My ${L().assets.toLowerCase()}` : TOOLS[t][1]);
const store = { get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }, set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* ignore */ } } };

// ---------- helpers ----------
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmtDate = (d) => { if (!d) return ""; const x = new Date(d.slice(0, 10)); return isNaN(x) ? d : x.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" }); };
const rupees = (n) => "₹" + Math.round(n || 0).toLocaleString("en-IN");
const spin = '<span class="spinner"></span>';
function toast(msg, kind = "", ms = 4200) {
  const t = $("#toast"); t.className = "toast " + kind; t.innerHTML = msg; t.classList.remove("hidden");
  clearTimeout(t._h); t._h = setTimeout(() => t.classList.add("hidden"), ms);
}
async function api(path, opts = {}) {
  const o = { ...opts };
  if (o.json) { o.method = o.method || "POST"; o.headers = { "Content-Type": "application/json" }; o.body = JSON.stringify(o.json); delete o.json; }
  const r = await fetch(path, o);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || `Request failed (${r.status})`);
  return data;
}
function tierBadge(t) { const [c, l] = TIER[t?.tier || t] || ["b-src", t?.tier || t]; return `<span class="badge ${c}" title="${esc(t?.label || "")}">${l}</span>`; }
function clearCharts() { S.charts.forEach((c) => c.destroy()); S.charts = []; }
const PALETTE = ["#e8833a", "#16202e", "#0f766e", "#1d4ed8", "#b91c1c", "#7c3aed", "#ca8a04", "#64748b"];
function pack() { return S.packs[S.ind]; }
const nm = (a) => { const n = String(a?.name || ""); return a?.id && n.startsWith(a.id) ? n.slice(a.id.length).replace(/^\s*[·:—-]\s*/, "") || n : n; };
function L() { return pack().labels; }
function assetOptions(selected, includeAll = false, includeAny = false) {
  const p = pack(); const bySite = {};
  p.assets.forEach((a) => { (bySite[a.site] = bySite[a.site] || []).push(a); });
  let h = includeAll ? `<option value="ALL">All ${esc(L().assets.toLowerCase())}</option>` : "";
  if (includeAny) h += `<option value="ANY" ${selected === "ANY" ? "selected" : ""}>🤷 Not sure — search everything</option>`;
  for (const s of p.sites) {
    h += `<optgroup label="${esc(s.name)}">` + (bySite[s.id] || []).map((a) => `<option value="${a.id}" ${a.id === selected ? "selected" : ""}>${esc(a.id)} — ${esc(nm(a))}</option>`).join("") + "</optgroup>";
  }
  return h;
}
function personOptions(selected) { return pack().people.map((p) => `<option value="${p.id}" ${p.id === selected ? "selected" : ""}>${esc(p.name)} — ${esc(p.role)}</option>`).join(""); }
function personName(id) { return (pack().people.find((p) => p.id === id) || {}).name || id; }
function roleObj() { return pack().roles.find((r) => r.id === S.role) || pack().roles[0]; }
function go(hash) { if (location.hash === hash) route(); else location.hash = hash; }

// ---------- voice & photo ----------
// Languages (menu label, Google/Chrome code). Sarvam does the real listening on the server; this list is for the menus.
const LANGS = { en: ["English", "en-IN"], hi: ["हिन्दी", "hi-IN"], hinglish: ["Hinglish", "hi-IN"], kn: ["ಕನ್ನಡ", "kn-IN"], ta: ["தமிழ்", "ta-IN"],
  te: ["తెలుగు", "te-IN"], mr: ["मराठी", "mr-IN"], bn: ["বাংলা", "bn-IN"], gu: ["ગુજરાતી", "gu-IN"], ml: ["മലയാളം", "ml-IN"], pa: ["ਪੰਜਾਬੀ", "pa-IN"], od: ["ଓଡ଼ିଆ", "or-IN"] };
const LANG_OF = { "hi-IN": "hi", "kn-IN": "kn", "ta-IN": "ta", "te-IN": "te", "mr-IN": "mr", "bn-IN": "bn", "gu-IN": "gu", "ml-IN": "ml", "pa-IN": "pa", "od-IN": "od", "en-IN": "en" };
let rec = null; // the recording in progress
const MAX_REC_MS = 28000, PAUSE_MS = 1500, NO_SPEECH_MS = 7000;
async function toggleVoice(btn, onText) {
  if (rec) { rec.stop("tap"); return; }
  if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) { toast("This browser can't record audio — type instead."); return; }
  let stream;
  try { stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 } }); }
  catch (e) { toast("Microphone not allowed: " + esc(e.message), "alert"); return; }
  const mime = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"].find((m) => MediaRecorder.isTypeSupported?.(m)) || "";
  const recorder = new MediaRecorder(stream, mime ? { mimeType: mime, audioBitsPerSecond: 64000 } : undefined);
  const chunks = []; recorder.ondataavailable = (e) => e.data.size && chunks.push(e.data);
  // the "listening" bar: sound level, timer, live words (desktop Chrome), stop button
  const pill = document.createElement("div"); pill.className = "listen";
  pill.innerHTML = `<div class="row" style="gap:10px;flex-wrap:nowrap"><span class="rec-dot"></span><b>Listening…</b><div class="lvl"><i></i></div><span class="mono small" id="lv-t">0:00</span>
    <button class="btn sm" id="lv-stop">■ Done</button></div><div class="small lv-txt" id="lv-txt">Speak in any language — it stops by itself when you pause.</div>`;
  document.body.appendChild(pill);
  const orig = btn.innerHTML; const big = btn.classList.contains("bigmic") || btn.classList.contains("hf-btn");
  btn.classList.add("rec"); btn.innerHTML = big ? "<span>■</span><b>Stop</b>" : "■";
  // sound level + pause detection (Web Audio)
  const Ctx = window.AudioContext || window.webkitAudioContext; let ctx = null, an = null, buf = null;
  try { ctx = new Ctx(); if (ctx.state === "suspended") ctx.resume(); an = ctx.createAnalyser(); an.fftSize = 1024; ctx.createMediaStreamSource(stream).connect(an); buf = new Float32Array(an.fftSize); } catch { an = null; }
  const t0 = Date.now(); let lastVoice = 0, voiced = 0, heard = false, floor = 0.006, raf = 0, why = "", alive = false;
  const tick = () => {
    const now = Date.now(), el = now - t0;
    let level = 0;
    if (an) { an.getFloatTimeDomainData(buf); let sum = 0; for (let i = 0; i < buf.length; i++) sum += buf[i] * buf[i]; level = Math.sqrt(sum / buf.length); }
    const thr = Math.max(0.012, floor * 2.5);
    if (level > 0.0003) alive = true;  // the meter really gets sound (some phones give silence here: then only ■ Done / 28 s stop it)
    if (level > thr) { voiced++; if (voiced >= 4) { heard = true; lastVoice = now; } } else { voiced = 0; floor = floor * 0.97 + level * 0.03; }
    pill.querySelector(".lvl i").style.width = Math.min(100, (level / 0.12) * 100) + "%";
    const left = Math.ceil((MAX_REC_MS - el) / 1000);
    $("#lv-t").textContent = `0:${String(Math.floor(el / 1000)).padStart(2, "0")}` + (left <= 8 ? ` · ${left}s left` : "");
    if (alive && heard && now - lastVoice > PAUSE_MS) return rec.stop("pause");
    if (alive && !heard && el > NO_SPEECH_MS) return rec.stop("silence");
    if (el > MAX_REC_MS) return rec.stop("limit");
    raf = requestAnimationFrame(tick);
  };
  // live words while speaking (Chrome on a computer; on phones two listeners can fight over the mic, so it's off there)
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition; let live = null;
  if (SR && !/Android|iPhone|iPad|iPod/i.test(navigator.userAgent)) {
    try { live = new SR(); live.lang = (LANGS[S.lang] || LANGS.en)[1]; live.interimResults = true; live.continuous = true;
      live.onresult = (e) => { let t = ""; for (const r of e.results) t += r[0].transcript; if (t.trim()) $("#lv-txt").innerHTML = `<i class="muted">${esc(t)}</i>`; };
      live.onerror = () => {}; live.start(); } catch { live = null; }
  }
  rec = { stop: (reason) => { if (why) return; why = reason || "tap"; cancelAnimationFrame(raf); try { live && live.stop(); } catch {} if (recorder.state !== "inactive") recorder.stop(); } };
  recorder.onstop = async () => {
    stream.getTracks().forEach((t) => t.stop()); try { ctx && ctx.close(); } catch {}
    rec = null; btn.classList.remove("rec");
    if (why === "silence" || !chunks.length) { pill.remove(); btn.innerHTML = orig; toast("Didn't hear anything — hold the phone closer and try again."); return; }
    pill.querySelector("b").textContent = "Understanding…"; pill.querySelector(".rec-dot").classList.add("busy"); $("#lv-stop").remove(); btn.innerHTML = big ? `${spin}<b>Understanding…</b>` : spin;
    try {
      const type = recorder.mimeType || mime || "audio/webm"; const ext = type.includes("mp4") ? "m4a" : type.includes("ogg") ? "ogg" : "webm";
      const fd = new FormData(); fd.append("audio", new Blob(chunks, { type }), "voice." + ext);
      fd.append("language", S.lang || "en"); if (S.ind) fd.append("industry", S.ind);
      const r = await api("/api/voice", { method: "POST", body: fd }); S.lastVoice = r; onText(r.text);
      const heardIn = r.language && r.language !== S.lang && r.language !== "en" ? ` · heard ${LANGS[r.language]?.[0] || r.language}` : "";
      toast(`🎙️ ${esc(r.engine)} · ${r.seconds}s${heardIn}${why === "limit" ? " · stopped at 28 s" : ""}: “${esc(r.text.slice(0, 120))}”`);
    } catch (e) { toast(esc(e.message), "alert"); }
    pill.remove(); btn.innerHTML = orig;
  };
  $("#lv-stop").onclick = () => rec && rec.stop("tap");
  recorder.start(250); raf = requestAnimationFrame(tick);
}
function pickPhoto(assetId, onResult) {
  const inp = document.createElement("input"); inp.type = "file"; inp.accept = "image/*"; inp.capture = "environment";
  inp.onchange = async () => {
    const f = inp.files[0]; if (!f) return; toast(spin + " Reading the photo…", "", 20000);
    try { const fd = new FormData(); fd.append("image", f); if (assetId) fd.append("asset_id", assetId);
      const r = await api(`/api/i/${S.ind}/photo`, { method: "POST", body: fd }); onResult(r); toast("📷 " + esc(r.what_i_see || "Read the photo."));
    } catch (e) { toast(esc(e.message), "alert"); }
  };
  inp.click();
}

// ---------- status ----------
async function loadStatus() {
  try {
    S.status = await api("/api/status");
    const m = $("#chip-mem"), l = $("#chip-llm"); const cloud = S.status.memory.startsWith("Hindsight");
    m.classList.toggle("on", cloud); m.classList.toggle("off", !cloud); m.lastElementChild.textContent = cloud ? "Hindsight memory" : "Practice memory (offline)";
    m.title = S.status.memory_error || (cloud ? "One Hindsight memory bank per industry" : "Add HINDSIGHT_API_KEY to use Hindsight Cloud");
    l.classList.toggle("on", !!S.status.llm); l.classList.toggle("off", !S.status.llm);
    l.lastElementChild.textContent = S.status.groq && S.status.sarvam ? "Groq + Sarvam on" : S.status.groq ? "Groq AI on" : S.status.sarvam ? "Sarvam AI on" : "AI off (rule-based)";
    l.title = S.status.llm ? S.status.llm_model : "Add GROQ_API_KEY for AI answers, voice and photos";
    const rd = $("#chip-ready"); if (rd) { rd.className = "chip simple-only " + (S.status.llm ? "on" : "off"); rd.lastElementChild.textContent = S.status.llm ? "Ready" : "Basic mode";
      rd.title = S.status.llm ? "Ustaad is ready" : "AI keys are not set — answers are simpler"; }
    const sv = $("#chip-save"), au = S.status.autosave || {};
    if (au.enabled) { sv.classList.remove("hidden"); const okk = au.ready && !au.last_error; sv.classList.toggle("on", okk); sv.classList.toggle("off", !okk);
      sv.lastElementChild.textContent = au.ready && !au.last_error ? "💾 Auto-save on" : "💾 Auto-save paused";
      sv.title = au.last_error || `Everything added here is saved to ${au.where}${au.last_saved ? " · last saved " + au.last_saved.replace("T", " ") : ""} and comes back after a restart.`; }
  } catch (e) { /* ignore */ }
}

// ---------- home ----------
async function renderHome() {
  const d = S.industries || (S.industries = await api("/api/industries"));
  const total = d.industries.reduce((a, i) => a + i.counts.records + i.counts.tips + i.counts.public, 0);
  app.innerHTML = `
  <section class="hero">
    <div>
      <div class="kicker">Expert memory for any industry</div>
      <h1>When your best expert leaves,<br>their know-how shouldn't.</h1>
      <p class="lead">Ustaad remembers what your senior people did and whether it worked — and tells the next person, by voice, in their language. It gets smarter every time someone taps <b>it worked</b> or <b>it didn't</b>.</p>
      <div class="row" style="margin-top:14px"><button class="btn accent big" id="try30">▶ Try it in 30 seconds</button>
        <span class="small muted">You become a new technician. A machine is whistling. See what Ustaad remembers.</span></div>
      <div id="home-roi" class="home-roi"></div>
    </div>
    <div class="loop">
      <div class="step"><b>🎙️ 1 · Say the problem</b><span class="small muted">Speak, type or take a photo — in your own language</span></div>
      <div class="step"><b>👷 2 · Get your team's fix</b><span class="small muted">What worked before, who did it, how many times</span></div>
      <div class="step"><b>✅ 3 · Tap "It worked"</b><span class="small muted">Good fixes rise, bad ones sink — the next person gets yours</span></div>
    </div>
  </section>
  <div class="panel-head"><h2>Choose your industry</h2><span class="small muted">${total.toLocaleString("en-IN")} memories across ${d.industries.length} industries · one Hindsight memory bank each</span></div>
  <div class="grid g3">
    ${d.industries.map((i) => `
      <a class="card ind-card" href="#/i/${i.id}" style="--c:${i.color}">
        <span class="ico">${i.icon}</span><h3>${esc(i.name)}</h3><span class="small muted">${esc(i.tagline)}</span>
        <span class="meta"><span class="badge b-src">${i.counts.records + i.counts.tips} team memories</span><span class="badge b-public">${i.counts.public} public records</span><span class="badge b-src">${i.sites.length} sites</span></span>
      </a>`).join("")}
    <div class="card" style="border-top:5px dashed #0e7490"><span class="ico" style="font-size:30px">＋</span><h3>Build your own industry</h3>
      <span class="small muted">Type any industry. Ustaad creates the roles, equipment and starter questions — memory starts empty and learns as people log work.</span>
      <div class="row" style="margin-top:10px"><input class="field" id="cu-name" placeholder="e.g. bakery, textile mill, solar farm" style="flex:1;min-width:140px"><button class="btn primary" id="cu-go">Create</button></div>
      <div class="row" style="margin-top:8px">${d.coming_soon.map((c) => `<span class="badge b-src">${c.icon} ${esc(c.name)}</span>`).join("")}</div></div>
  </div>
  <h2 style="margin-top:28px">What could Ustaad save you?</h2>
  <div class="card"><div class="roi">
    <div><label class="f">Breakdowns / problems per month</label><input class="field" id="roi-n" type="number" value="20"></div>
    <div><label class="f">Hours lost each time</label><input class="field" id="roi-h" type="number" value="2" step="0.5"></div>
    <div><label class="f">Cost of one lost hour (₹)</label><input class="field" id="roi-c" type="number" value="6000"></div>
    <div><label class="f">Time saved with Ustaad (%)</label><input class="field" id="roi-p" type="number" value="40"></div>
    <div class="out"><span class="small">Estimated saving per year</span><b id="roi-out">—</b><span class="tiny" style="opacity:.75">Demo factory data shows repair time falling about 50% after Ustaad started. Your result will differ.</span></div>
  </div></div>
  <p class="tiny muted" style="margin-top:20px">Demo data: people and companies are fictional; facts come from public sources (ISO 10816, FSSAI, WHO checklist, FDA MAUDE, NHTSA, NYC inspections, Zomato reviews, public post-mortems, Microsoft Azure & AI4I datasets).</p>`;
  api("/api/i/factory/stats").then((d) => { const r = d.roi || {}; const box = $("#home-roi"); if (!box) return;
    box.innerHTML = `<span class="tiny muted">In the sample factory since Ustaad started:</span>
      <span><b>${r.hours_saved} h</b> downtime saved</span><span><b>${r.repeat_failures_avoided}</b> repeat failures avoided</span>
      <span><b>${r.fixed_rate}%</b> of fixes worked</span><span><b>${rupees(d.money_saved)}</b> saved</span>`; }).catch(() => {});
  $("#try30").onclick = () => { S.prefill = { asset_id: "CNC-3", problem: "CNC-3 alarm 2041 with a whistling sound at high rpm", auto: true }; go("#/i/factory/technician/ask"); };
  $("#cu-go").onclick = async () => {
    const btn = $("#cu-go"); btn.disabled = true; btn.innerHTML = spin;
    try { const r = await api("/api/packs/custom", { json: { name: $("#cu-name").value } }); S.industries = null; delete S.packs[r.id];
      toast(`✔ Created ${esc(r.name)} (${esc(r.generated_by)}). Memory is empty — log work and watch it learn.`); go(`#/i/${r.id}`); }
    catch (e) { toast(esc(e.message), "alert"); btn.disabled = false; btn.textContent = "Create"; }
  };
  const calc = () => { const n = +$("#roi-n").value, h = +$("#roi-h").value, c = +$("#roi-c").value, p = +$("#roi-p").value;
    $("#roi-out").textContent = rupees(n * 12 * h * c * p / 100); };
  $$(".roi input").forEach((i) => (i.oninput = calc)); calc();
}

// ---------- industry: role picker ----------
async function loadPack(ind) { if (!S.packs[ind]) S.packs[ind] = await api(`/api/i/${ind}/pack`); S.ind = ind; return S.packs[ind]; }
async function renderRoles(ind) {
  const p = await loadPack(ind);
  app.innerHTML = `
  <div class="crumbs"><a href="#/">Industries</a> › <span>${esc(p.name)}</span></div>
  <div class="panel-head"><div><h1 style="font-size:34px">${p.icon} ${esc(p.org.name)}</h1><p class="muted">${esc(p.org.note)}</p></div>
    <div class="row">${p.sites.map((s) => `<span class="badge b-site">📍 ${esc(s.name)}</span>`).join("")}</div></div>
  ${p.banner ? `<div class="banner" style="margin-bottom:14px">🛡️ ${esc(p.banner)}</div>` : ""}
  <h2>Who are you today?</h2><p class="muted small" style="margin-top:-4px">Pick one. First time here? Start as the first one — the person on the floor.</p>
  <div class="grid g3">${p.roles.map((r, i) => `
    <button class="role-card ${i === 0 && !r.can_approve ? "rec" : ""}" data-role="${r.id}">${i === 0 && !r.can_approve ? '<span class="badge b-verified" style="float:right">Start here</span>' : ""}<h3>${esc(r.name)}</h3>
      <span class="small">${r.can_approve ? "Senior: uses knowledge, approves new memories, adds machines." : "On the floor: asks Ustaad, tells it what worked."}</span>
      <div class="tools">${r.tools.slice(0, 6).map((t) => `<span class="badge b-src">${TOOLS[t][0]} ${t === "machines" ? "My " + esc(p.labels.assets.toLowerCase()) : TOOLS[t][1]}</span>`).join("")}</div></button>`).join("")}
  </div>
  <h2 style="margin-top:26px">The people</h2>
  <div class="grid g4">${p.people.map((x) => `<div class="card"><b>${esc(x.name)}</b><div class="small muted">${esc(x.role)}</div>
    <div class="small">${x.experience_years} yrs · ${esc(x.speciality)}</div>${x.retiring_on ? `<span class="badge b-high" style="margin-top:6px">Leaving ${fmtDate(x.retiring_on)}</span>` : ""}</div>`).join("")}</div>`;
  $$(".role-card").forEach((b) => (b.onclick = () => { const r = p.roles.find((x) => x.id === b.dataset.role); go(`#/i/${ind}/${r.id}/${r.tools[0]}`); }));
}

// ---------- workspace ----------
function defaultPerson(role) {
  const ppl = pack().people; const r = pack().roles.find((x) => x.id === role);
  if (r?.can_approve) return (ppl.find((p) => !p.retiring_on) || ppl[0]).id;
  return [...ppl].sort((a, b) => a.experience_years - b.experience_years)[0].id;  // workers: the newest joiner
}
function sideLinks(ind, role, tools, tool) {
  const link = (t) => `<a href="#/i/${ind}/${role}/${t}" class="${t === tool ? "on" : ""}"><span>${TOOLS[t][0]}</span><span>${esc(toolName(t))}</span></a>`;
  const r = pack().roles.find((x) => x.id === role) || {};
  const main = ["ask", "log", "machines", ...(r.can_approve ? ["approvals", "stats"] : [])].filter((t) => tools.includes(t));
  const rest = tools.filter((t) => !main.includes(t) && TOOLS[t]);
  const open = rest.includes(tool) || store.get("ustaad-more") === "1";
  let h = main.map(link).join("");
  if (rest.length) {
    h += `<details class="more" ${open ? "open" : ""}><summary>☰ More tools <span class="tiny muted">(${rest.length})</span></summary>`;
    for (const [name, ids] of GROUPS) { const mine = ids.filter((t) => rest.includes(t)); if (mine.length) h += `<div class="grp">${name}</div>` + mine.map(link).join(""); }
    const other = rest.filter((t) => !GROUPS.some(([, ids]) => ids.includes(t)));
    if (other.length) h += `<div class="grp">Data & tools</div>` + other.map(link).join("");
    h += "</details>";
  }
  h += `<a href="#" class="more-m" id="more-m"><span>☰</span><span>More</span></a>`;
  return h;
}
function moreSheet(ind, role, tools) {
  $("#pg-drawer")?.remove(); const dr = document.createElement("div"); dr.id = "pg-drawer"; dr.className = "drawer";
  dr.innerHTML = `<div class="row" style="justify-content:space-between"><b>☰ All tools</b><button class="btn sm" id="pg-x">✕</button></div>
    <div class="sheet-grid">${tools.filter((t) => TOOLS[t]).map((t) => `<a class="sheet-item" href="#/i/${ind}/${role}/${t}"><span>${TOOLS[t][0]}</span><b>${esc(toolName(t))}</b><span class="tiny muted">${esc((HELP[t] || "").split(".")[0])}</span></a>`).join("")}
      <a class="sheet-item" href="#/connect"><span>🤖</span><b>Connect your AI</b><span class="tiny muted">Use this memory inside ChatGPT, Claude or Gemini</span></a></div>`;
  document.body.appendChild(dr); $("#pg-x").onclick = () => dr.remove(); $$("a", dr).forEach((a) => (a.onclick = () => dr.remove()));
  uiTranslate(dr);
}
async function renderWorkspace(ind, role, tool, sub) {
  const p = await loadPack(ind);
  if (S.role !== role || !S.person || !p.people.find((x) => x.id === S.person)) { S.role = role; S.person = defaultPerson(role); }
  const r = roleObj(); if (!r.tools.includes(tool)) tool = r.tools[0];
  app.innerHTML = `
  <div class="crumbs"><a href="#/">Industries</a> › <a href="#/i/${ind}">${esc(p.name)}</a> › <span>${esc(r.name)}</span> › <b>${esc(toolName(tool))}</b></div>
  <div class="ws">
    <nav class="side">
      <div class="who"><div class="tiny muted" data-notr>${p.icon} ${esc(p.org.name)}</div><label class="tiny muted" style="display:block;margin-top:6px">You are</label>
        <select id="who" class="field" style="padding:5px 8px;font-size:13px">${personOptions(S.person)}</select></div>
      ${sideLinks(ind, role, r.tools, tool)}
    </nav>
    <section id="panel">${p.banner ? `<div class="banner" style="margin-bottom:12px">🛡️ ${esc(p.banner)}</div>` : ""}
      ${HELP[tool] ? `<div class="help no-print">ⓘ <b>What is this?</b> ${esc(HELP[tool])}</div>` : ""}<div id="tool"></div></section>
  </div>`;
  $("#who").onchange = (e) => { S.person = e.target.value; };
  const mm = $("#more-m"); if (mm) mm.onclick = (e) => { e.preventDefault(); moreSheet(ind, role, r.tools); };
  const md = $(".side details.more"); if (md) md.ontoggle = () => store.set("ustaad-more", md.open ? "1" : "0");
  clearCharts();
  const el = $("#tool");
  try { await (VIEWS[tool] || VIEWS.ask)(el, sub); } catch (e) { el.innerHTML = friendlyError(e, () => renderWorkspace(ind, role, tool, sub)); bindRetry(el); }
}
let _retry = null;
function friendlyError(e, retry) {
  _retry = retry;
  const net = /fetch|network|Failed to/i.test(e.message);
  return `<div class="card empty-state"><div style="font-size:34px">${net ? "📶" : "🤔"}</div><b>${net ? "No connection right now." : "This didn't load."}</b>
    <p class="small muted">${net ? "Check your internet, then try again." : esc(e.message)}</p><button class="btn accent" data-retry>↻ Try again</button></div>`;
}
function bindRetry(root) { $$("[data-retry]", root).forEach((b) => (b.onclick = () => _retry && _retry())); }

// ---------- ask ----------
const VIEWS = {};
VIEWS.ask = async (el) => {
  const p = pack(); const pre = S.prefill || {}; S.prefill = null;
  const aid = pre.asset_id || "ANY";
  el.innerHTML = `
  <div class="row" style="margin-bottom:10px;gap:8px"><button class="btn" id="a-brief">📢 Today's briefing</button><button class="btn" id="a-hands">🎧 Hands-free mode</button></div>
  <div id="a-briefout"></div>
  <div class="askhero card">
    <h2 class="ask-title">What's wrong?</h2>
    <p class="muted small" style="margin-top:-4px">Tell it like you'd tell a senior — speak, take a photo, or type. Any language.</p>
    <div class="ask-actions">
      <button class="bigmic" id="a-mic" aria-label="Tap and speak"><span>🎙️</span><b>Tap and speak</b></button>
      <button class="bigcam" id="a-cam" aria-label="Take a photo"><span>📷</span><b>Photo</b></button>
    </div>
    <textarea id="a-q" class="field bigfield" placeholder="…or type here, e.g. ${esc(p.questions[0])}">${esc(pre.problem || "")}</textarea>
    <div class="row" style="margin-top:10px;align-items:flex-end">
      <div style="flex:1;min-width:200px"><label class="f">Which ${esc(L().asset.toLowerCase())}? <span class="muted small">(skip if not sure)</span></label><select id="a-asset" class="field">${assetOptions(aid, false, true)}</select></div>
      <button class="btn accent big" id="a-go">Get the fix →</button></div>
    <details class="moreopts" ${pre.expert_id ? "open" : ""}><summary>More options</summary>
      <label class="f" style="margin-top:6px">Ask one expert's experience <span class="muted small">(only their own fixes)</span></label>
      <select id="a-expert" class="field"><option value="">Everyone in the team</option>${p.people.map((x) => `<option value="${x.id}" ${x.id === pre.expert_id ? "selected" : ""}>${esc(x.name)} — ${esc(x.role)}${x.retiring_on ? ` · leaving ${fmtDate(x.retiring_on)}` : ""}</option>`).join("")}</select></details>
    <div class="row" style="margin-top:10px"><span class="tiny muted">Or try:</span>${p.questions.map((q) => `<button class="sample">${esc(q)}</button>`).join("")}</div>
    <div class="row eng-only" style="margin-top:10px"><span class="tiny muted">Engineer view:</span><div class="toggle" id="memtog"><button class="on" data-v="1">Memory ON</button><button data-v="0">Memory OFF (plain chatbot)</button></div></div>
    <div id="a-photo" class="small muted"></div>
  </div>
  <div id="a-out" style="margin-top:16px"></div>`;
  $("#a-brief").onclick = () => playBriefing($("#a-briefout"));
  $("#a-hands").onclick = () => handsFree($("#a-asset").value);
  let useMem = true;
  $$("#memtog button").forEach((b) => (b.onclick = () => { useMem = b.dataset.v === "1"; $$("#memtog button").forEach((x) => x.classList.toggle("on", x === b)); b.classList.toggle("off-state", !useMem); }));
  $$(".sample", el).forEach((b) => (b.onclick = () => {
    $("#a-q").value = b.textContent; const m = b.textContent.match(/\b([A-Z]{2,4}-[A-Z0-9]+)\b/);
    if (m && p.assets.find((a) => a.id === m[1])) $("#a-asset").value = m[1];
  }));
  $("#a-mic").onclick = (e) => toggleVoice(e.currentTarget, (t) => { $("#a-q").value = t; $("#a-go").click(); });
  $("#a-cam").onclick = () => pickPhoto($("#a-asset").value, (r) => { $("#a-q").value = r.suggested_question || r.what_i_see; $("#a-photo").innerHTML = `📷 <b>I see:</b> ${esc(r.what_i_see)} <span class="tiny muted">(${esc(r.read_by || "")})</span> ${(r.codes || []).map((c) => `<span class="badge b-src mono">${esc(c)}</span>`).join(" ")}`; });
  $("#a-go").onclick = async () => {
    const btn = $("#a-go"); if (!$("#a-q").value.trim()) { toast("Tell Ustaad the problem first — tap 🎙️ and speak, or type."); $("#a-q").focus(); return; }
    btn.disabled = true; $("#a-out").innerHTML = `<div class="card">${spin} ${useMem ? "Looking through your team's experience…" : "Asking a general chatbot…"}</div>`;
    try {
      const res = await api(`/api/i/${S.ind}/ask`, { json: { asset_id: $("#a-asset").value, problem: $("#a-q").value, use_memory: useMem, language: S.lang, expert_id: $("#a-expert")?.value || "" } });
      S.lastAsk = res; renderAnswer($("#a-out"), res); guideHook("asked", res); uiTranslate($("#a-out"));
      $("#a-out").scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (e) { $("#a-out").innerHTML = friendlyError(e, () => $("#a-go").click()); bindRetry($("#a-out")); }
    btn.disabled = false;
  };
  if (pre.problem && pre.auto) $("#a-go").click();
};

function renderAnswer(out, res) {
  if (res.mode === "chart") {
    out.innerHTML = `<div class="card"><div class="trust verified">📊 Answered from exact records</div><h3 style="margin-top:12px">${esc(res.chart.title)}</h3>
      <div id="ans-chart"></div><p>${esc(res.chart.summary)}</p></div>`;
    (res.chart.dimension === "month" ? MC.vbar : MC.hbar)($("#ans-chart"), { labels: res.chart.labels, values: res.chart.values, unit: res.chart.unit });
    return;
  }
  const a = res.answer, t = res.trust;
  if (t.level === "offtopic") {
    out.innerHTML = `<div class="card answer"><div class="trust offtopic">🛑 ${esc(t.label)}</div>
      <p style="font-size:16px;margin-top:12px">${esc(a.summary)}</p>
      <p class="small muted">Ustaad answers work problems at ${esc(pack().org.name)}. Try one of these:</p>
      <div class="row">${pack().questions.map((q) => `<button class="sample" data-q="${esc(q)}">${esc(q)}</button>`).join("")}</div>
      <p class="tiny muted" style="margin-top:10px">Written by ${esc(res.written_by)}</p></div>`;
    $$("[data-q]", out).forEach((b) => (b.onclick = () => { $("#a-q").value = b.dataset.q; window.scrollTo({ top: 0, behavior: "smooth" }); }));
    return;
  }
  const refs = (arr) => (arr || []).map((r) => `<span class="ref" data-ref="${esc(r)}">${esc(r)}</span>`).join("");
  const used = res.memories.filter((m) => m.used), other = res.memories.filter((m) => !m.used);
  const icon = { verified: "✔", off: "○", new: "✚" }[t.level] || "◐";
  const parts = a.parts_status || [];
  const first = a.check_first || (a.steps || [])[0] || "";
  const steps = a.check_first ? (a.steps || []) : (a.steps || []).slice(1);
  const g = res.diagnosis, top = g && g.check_order[0];
  const voiceStep = S.lastVoice && S.lastVoice.text && res.problem && res.problem.startsWith(S.lastVoice.text.slice(0, 20)) ? S.lastVoice : null;
  out.innerHTML = `
  <div class="grid" style="grid-template-columns:minmax(0,1.5fr) minmax(0,1fr)" id="ans-grid">
    <div class="card answer">
      <div class="trust ${t.level}">${icon} ${esc(t.label)}</div>
      ${res.expert ? `<div class="expertline">🧓 From <b>${esc(res.expert.name)}</b>'s own records — not ${esc(res.expert.name.split(" ")[0])} in person.${res.expert.leaving ? ` Leaving ${fmtDate(res.expert.leaving)} — this is how the know-how stays.` : ""}</div>` : ""}
      ${first ? `<div class="doit"><span class="doit-k">👉 Do this first</span><span class="doit-v" data-tr>${esc(first)}</span></div>` : ""}
      <p class="ans-sum" data-tr>${esc(a.summary)}</p>
      ${top ? `<div class="usually">🎯 Usually it's <b data-tr>${esc(top.label)}</b> — ${Math.round(top.p * 100)}% of ${g.cases} past case${g.cases === 1 ? "" : "s"} like this. <a href="#" data-open-why>Why?</a></div>` : ""}
      ${a.safety && steps.length ? `<div class="safetygate" id="sg"><b>🛡️ Before you start — tick these</b>
        <label><input type="checkbox" class="sg"><span data-tr>${esc(a.safety)}</span></label>
        <label><input type="checkbox" class="sg"><span>I'm wearing the right gloves and goggles</span></label>
        <label><input type="checkbox" class="sg"><span>Someone knows I'm working on this</span></label>
        <div class="tiny muted">The steps unlock after these checks.${res.asset?.id && res.asset.id !== "ANY" ? ` <a href="#" data-quiz="${esc(res.asset.id)}">🎓 New to ${esc(res.asset.id)}? Take the 5-question check first.</a>` : ""}</div></div>` : ""}
      ${steps.length ? `<h3 style="margin-top:14px">Then, step by step <span class="tiny muted">(tick as you go)</span></h3>
        <ul class="checklist ${a.safety ? "locked" : ""}" id="steps">${steps.map((s2, i) => `<li><label><input type="checkbox" data-i="${i + 1}"><span data-tr>${esc(s2)}</span></label></li>`).join("")}</ul>` : ""}
      ${parts.length ? `<div class="partsbox">📦 <b>Spare parts:</b> ${parts.map((x) => `<span class="badge ${x.status === "out" ? "b-failed" : x.status === "low" ? "b-unreviewed" : "b-verified"}">${esc(x.name)}${x.part_no ? " · " + esc(x.part_no) : ""} — ${x.status === "out" ? "0 in store, order now" : x.status === "low" ? `only ${x.stock} left` : x.status === "ok" ? `${x.stock} in store` : "stock unknown"}</span>`).join(" ")}</div>` : ""}
      ${a.safety && !steps.length ? `<div class="safety">🦺 <span data-tr>${esc(a.safety)}</span></div>` : ""}
      ${res.use_memory ? `<div class="card fbbox" id="fb">
        <b class="fb-q">Did it work?</b> <span class="small muted">Your answer teaches Ustaad — the next person gets it.</span>
        <div class="row fb-btns"><button class="btn ok big" id="fb-ok">✔ Yes, it worked</button><button class="btn bad big" id="fb-no">✖ No, it didn't</button></div>
        <details class="fb-more"><summary>Add details (optional)</summary>
          ${res.asset.id === "ANY" ? `<div style="margin-top:8px"><label class="f">Which ${esc(L().asset.toLowerCase())} was it?</label><select id="fb-asset" class="field">${assetOptions(guessAsset(res))}</select></div>` : ""}
          <div class="row" style="margin-top:8px"><select id="fb-who" class="field" style="max-width:260px">${personOptions(S.person)}</select>
            <input id="fb-min" class="field" type="number" placeholder="Minutes it took" style="max-width:150px">
            <input id="fb-note" class="field" placeholder="What you actually did" style="flex:1;min-width:180px"></div></details></div>` : ""}
      <details class="why"><summary>Why we think so — chances, what not to repeat, the manual, expert tip</summary>
        ${a.manual_vs_team ? `<div class="mvt">📘 vs 🧑‍🔧 <b>Manual says vs. team found:</b> <span data-tr>${esc(a.manual_vs_team)}</span></div>` : ""}
        ${g ? diagCard(g) : ""}
        ${a.likely_causes?.length ? `<h3>Likely causes</h3><ul>${a.likely_causes.map((c) => `<li><b data-tr>${esc(c.cause)}</b> <span class="badge ${c.confidence === "high" ? "b-verified" : c.confidence === "medium" ? "b-tested" : "b-self"}">${esc(c.confidence)}</span>${refs(c.memory_refs)}<div class="small muted" data-tr>${esc(c.why)}</div></li>`).join("")}</ul>` : ""}
        ${a.avoid?.length ? `<h3>Don't repeat</h3><ul class="avoid">${a.avoid.map((x) => `<li><span data-tr>${esc(x.action)}</span>${refs(x.memory_refs)}<div class="small muted" data-tr>${esc(x.why)}</div></li>`).join("")}</ul>` : ""}
        ${a.expert_tip ? `<div class="tipbox" style="margin-top:12px">💡 <b>Expert tip:</b> <span data-tr>${esc(a.expert_tip)}</span></div>` : ""}
        ${a.estimated_time ? `<p class="small muted">⏱ Usually takes: ${esc(a.estimated_time)}</p>` : ""}
      </details>
      <div class="row no-print" style="margin-top:10px">${S.status?.sarvam ? '<button class="btn accent" id="btn-listen">🔊 Listen</button>' : ""}<span class="small muted">🌐</span>
        <select data-notr class="field" id="tl-pick" style="width:auto;padding:6px 10px" aria-label="Answer language">${Object.entries(LANGS).map(([k, v]) => `<option value="${k}" ${k === (res.shown_lang || res.language || "en") ? "selected" : ""}>${v[0]}</option>`).join("")}</select></div>
      <details class="eng-only trace"><summary>🔬 How this answer was made${res.total_ms ? ` — ${(res.total_ms / 1000).toFixed(1)} s` : ""}</summary>
        <ol class="trace-list">${voiceStep ? `<li><b>Heard your voice</b> <span class="tiny muted">${esc(voiceStep.engine)} · ${voiceStep.seconds}s${(voiceStep.tries || []).length > 1 ? " · tried " + voiceStep.tries.map((x) => x.engine + (x.ok ? " ✓" : " ✗")).join(" → ") : ""}</span></li>` : ""}
          ${(res.trace || []).map((x) => `<li><b>${esc(x.step)}</b> <span class="tiny muted">${esc(x.detail)}${x.ms ? ` · ${x.ms} ms` : ""}</span></li>`).join("")}</ol>
        <div class="tiny muted">Written by ${esc(res.written_by)}${res.translated_by ? ` in English · translated by ${esc(res.translated_by)}` : ""} · memory: ${esc(res.memory_mode)}${res.question_translated ? ` · question read as: “${esc(res.problem_en)}”` : ""}</div>
        <details><summary class="tiny">{ } Raw answer data</summary><pre class="pg-text" style="max-height:260px;overflow:auto">${esc(JSON.stringify({ answer: res.answer_en || res.answer, trust: res.trust, diagnosis: res.diagnosis }, null, 1))}</pre></details></details>
    </div>
    <div><div class="panel-head" style="margin-bottom:8px"><h3 style="margin:0">Where this comes from</h3><span class="small muted">${used.length} from your team${other.length ? ` · ${other.length} more checked` : ""}</span></div>
      <div id="mems">${used.length ? used.map(memCard).join("") : `<div class="card small muted">${res.use_memory ? "Nothing in your team's memory matches this exact problem — the advice is general. When you fix it, tap “Yes, it worked” so the next person gets your fix." : "Memory is OFF — this is what a plain chatbot knows."}</div>`}
      ${other.length ? `<details class="also"><summary>Also checked — not about this problem (${other.length})</summary>${other.map(memCard).join("")}</details>` : ""}</div>
      ${netCard(res.other_plants)}</div>
  </div>`;
  bindNetShare(out);
  const ow = $("[data-open-why]", out); if (ow) ow.onclick = (e) => { e.preventDefault(); const w = $("details.why", out); w.open = true; w.scrollIntoView({ behavior: "smooth", block: "start" }); };
  const sgs = $$(".sg", out);
  const unlock = () => { const okk = sgs.every((x) => x.checked); $("#steps", out)?.classList.toggle("locked", !okk); $$("#steps input", out).forEach((x) => (x.disabled = !okk)); if (okk && sgs.length) $("#sg").classList.add("done"); };
  sgs.forEach((x) => (x.onchange = unlock)); if (sgs.length) unlock();
  $$("[data-quiz]", out).forEach((b) => (b.onclick = (e) => { e.preventDefault(); S.prefill = { quiz_asset: b.dataset.quiz }; go(`#/i/${S.ind}/${S.role}/quiz`); }));
  $$("#steps input", out).forEach((c) => (c.onchange = () => { c.closest("li").classList.toggle("done", c.checked);
    if ($$("#steps input", out).every((x) => x.checked)) { toast("All steps done — did it work? 👇"); $("#fb")?.scrollIntoView({ behavior: "smooth", block: "center" }); } }));
  if (window.innerWidth < 900) $("#ans-grid").style.gridTemplateColumns = "1fr";
  $$(".ref", out).forEach((r) => (r.onclick = () => { const m = $(`#mems [data-ref="${r.dataset.ref}"]`); if (m) { const d = m.closest("details"); if (d) d.open = true; $$("#mems .mem").forEach((x) => x.classList.remove("hl")); m.classList.add("hl"); m.scrollIntoView({ behavior: "smooth", block: "center" }); } }));
  bindMemButtons(out);
  out.dataset.lang = res.shown_lang || res.language || "en";
  const tl = $("#tl-pick", out);
  if (tl) tl.onchange = async () => {  // always start again from the English original, then translate (Sarvam)
    const to = tl.value, en = { ...res, answer: res.answer_en || res.answer, answer_en: null, translated_by: null, shown_lang: to };
    if (res.answer_en || to === "en") renderAnswer(out, en);
    if (to !== "en") { const o = out; o.dataset.lang = to; const w = $("details.why", o); if (w) w.open = true; await translateBlock(o, to, $("#tl-pick", o)); }
  };
  const lb = $("#btn-listen");
  if (lb) lb.onclick = async () => {
    const parts2 = $$("[data-tr]", out).slice(0, 8).map((n) => n.textContent);
    const lang = out.dataset.lang === "hinglish" ? "hi" : (out.dataset.lang || "en");
    lb.disabled = true; lb.innerHTML = spin;
    try { const r = await api("/api/speak", { json: { text: parts2.join(". "), language: lang } });
      const au = new Audio(`data:${r.mime};base64,${r.audio}`); au.play(); }
    catch (e) { toast(esc(e.message), "alert"); }
    lb.disabled = false; lb.innerHTML = "🔊 Listen";
  };
  const send = async (result) => {
    const steps = $$("#steps input:checked").map((c) => +c.dataset.i);
    try {
      const r = await api(`/api/i/${S.ind}/feedback`, { json: { ask_id: res.ask_id, result, person_id: $("#fb-who").value, downtime_minutes: +$("#fb-min").value || 0, action_done: $("#fb-note").value, steps_done: steps, asset_id: $("#fb-asset")?.value } });
      const ex = r.expert;
      $("#fb").innerHTML = `<b class="fb-q">${result === "fixed" ? "✔ Thank you — saved as WORKED" : "✖ Saved as DIDN'T WORK"}</b><p class="small">${esc(r.message)}</p><p class="tiny muted eng-only">Saved to: ${esc(r.saved_to)}</p>
        ${ex ? `<div class="expertbox">📞 <b>Ask the expert:</b> ${esc(ex.name)} (${esc(ex.role)}) has fixed ${esc(ex.about)} ${ex.fixes} time(s).${ex.failed_times >= 2 ? ` This has now failed ${ex.failed_times} times — time to call.` : ""}
          <div class="row" style="margin-top:8px"><a class="btn ok sm" target="_blank" rel="noopener" href="https://wa.me/?text=${encodeURIComponent(ex.message)}">💬 Send on WhatsApp</a>
          <span class="tiny muted">Opens WhatsApp with the message ready — you choose ${esc(ex.name.split(" ")[0])} from your contacts.</span></div></div>` : ""}`;
      guideHook("feedback", r);
    } catch (e) { toast(esc(e.message), "alert"); }
  };
  if ($("#fb-ok")) { $("#fb-ok").onclick = () => send("fixed"); $("#fb-no").onclick = () => send("failed_again"); }
}
function guessAsset(res) {  // the worker's own site first, then the best match, then the first item
  const me = pack().people.find((p) => p.id === S.person) || {};
  const real = res.memories.filter((m) => m.asset_id && m.asset_id !== "ALL" && pack().assets.find((a) => a.id === m.asset_id));
  const mine = real.find((m) => (pack().assets.find((a) => a.id === m.asset_id) || {}).site === me.site);
  return (mine || real[0] || {}).asset_id || pack().assets[0].id;
}
function memCard(m) {
  const tier = m.trust || { tier: m.kind === "public" ? "public" : "tested" };
  return `<div class="mem ${m.kind === "insight" ? "insight" : ""}" data-ref="${esc(m.ref)}" data-key="${esc(m.key)}">
    <div class="top">${m.ref ? `<span class="ref">${esc(m.ref)}</span>` : ""}${tierBadge(tier)}
      ${m.kind === "tip" ? '<span class="badge b-src">💡 Expert tip</span>' : ""}
      ${m.cross_site ? `<span class="badge b-site">🌐 Learned at ${esc(m.site)}</span>` : m.site ? `<span class="badge b-src">📍 ${esc(m.site)}</span>` : ""}
      ${m.other_asset ? `<span class="badge b-unreviewed">↪ Found on ${esc(m.other_asset)}</span>` : ""}
      ${m.aging ? `<span class="badge ${m.aging.level === "fresh" ? "b-verified" : m.aging.level === "faded" ? "b-failed" : "b-unreviewed"}" title="Memories age: old or contradicted fixes lose trust">${esc(m.aging.label)}</span>` : ""}
      ${m.source && !/^public record$/i.test(m.source) ? `<span class="badge b-src" title="Source">📚 ${esc(m.source.slice(0, 48))}</span>` : ""}
      ${m.flagged ? '<span class="badge b-failed">Flagged</span>' : ""}</div>
    <div class="who">${esc(m.problem || (m.fact || m.text || "").slice(0, 80))}</div>
    ${m.kind === "insight" ? `<div class="tiny muted">${m.trust?.tier === "hfact" ? "Saved in Hindsight earlier." : "Hindsight noticed this pattern across many memories by itself."}</div>` : `<div class="small">${esc((m.action || "").slice(0, 260))}</div>`}
    <div class="tiny muted">${esc(m.person || "")}${m.date ? " · " + fmtDate(m.date) : ""}${m.asset_id && m.asset_id !== "ALL" ? " · " + esc(m.asset_id) : ""}${m.origin ? " · from " + esc(m.origin) : ""}</div>
    <details><summary>Show source text</summary><p class="small">${esc(m.text)}</p>${m.url ? `<a class="small" href="${esc(m.url)}" target="_blank" rel="noopener">Open public source ↗</a>` : ""}
      <div class="row" style="margin-top:6px"><button class="btn sm" data-flag="${esc(m.key)}" data-un="${m.flagged ? 1 : 0}">${m.flagged ? "Restore" : "⚑ Flag as wrong"}</button></div></details>
  </div>`;
}
function bindMemButtons(root) {
  $$("[data-flag]", root).forEach((b) => (b.onclick = async () => {
    const un = b.dataset.un === "1";
    try { const r = await api(`/api/i/${S.ind}/flag`, { json: { key: b.dataset.flag, reason: "wrong", by: S.person, unflag: un } }); toast(esc(r.message)); b.textContent = un ? "⚑ Flag as wrong" : "Restore"; b.dataset.un = un ? "0" : "1"; }
    catch (e) { toast(esc(e.message), "alert"); }
  }));
}
async function translateBlock(root, lang, btn) {
  const nodes = $$("[data-tr]", root); if (!nodes.length) return;
  nodes.forEach((n) => { if (!n.dataset.orig) n.dataset.orig = n.textContent; });
  if (lang === "en") { nodes.forEach((n) => (n.textContent = n.dataset.orig)); return; }
  btn.disabled = true;
  try { const r = await api("/api/translate", { json: { texts: nodes.map((n) => n.dataset.orig), language: lang } });
    nodes.forEach((n, i) => (n.textContent = r.texts[i])); if (r.note) toast(esc(r.note)); }
  catch (e) { toast(esc(e.message), "alert"); }
  btn.disabled = false;
}

// ---------- log work ----------
VIEWS.log = async (el) => {
  el.innerHTML = `
  <div class="panel-head"><div><h2>I fixed something</h2><p class="muted small">Just say what happened. Ustaad tags the right ${esc(L().asset.toLowerCase())} and problem by itself.</p></div></div>
  <div class="grid g2 capture2">
    <label class="card bigcap"><span class="pic">📓</span><b>Scan an old logbook page</b><span class="small muted">Photo of a handwritten register — each line becomes a memory</span><input type="file" id="lb-file" accept="image/*" capture="environment" hidden></label>
    <label class="card bigcap"><span class="pic">🎥</span><b>Make a guide from a video</b><span class="small muted">Film the fix while you explain — get steps with photos</span><input type="file" id="vg-file" accept="video/*" hidden></label>
  </div><div id="cap-out" style="margin:12px 0"></div>
  <div class="card stack">
    <label class="f">Speak or type, any language</label>
    <textarea id="l-text" class="field" placeholder="e.g. ${esc(pack().assets[0].id)} ka problem phir aaya, filter saaf kiya, 20 minute mein theek ho gaya"></textarea>
    <div class="row"><button class="iconbtn" id="l-mic">🎙️</button><button class="btn accent" id="l-go">Save to memory</button>
      <span class="small muted">New memories show as <span class="badge b-unreviewed">Unreviewed</span> until a senior approves.</span></div>
    <div id="l-out"></div>
  </div>
  <div class="grid g2" style="margin-top:16px">
    <div class="card stack"><h3>💡 Add an expert tip</h3>
      <select id="t-asset" class="field">${assetOptions("", true)}</select>
      <textarea id="t-text" class="field" placeholder="A trick, a check, a warning — in your own words"></textarea>
      <input id="t-src" class="field" placeholder="Source, if any (manual, standard, regulation)">
      <div class="row"><button class="iconbtn" id="t-mic">🎙️</button><button class="btn primary" id="t-go">Save tip</button></div><div id="t-out" class="small"></div></div>
    <div class="card stack"><h3>📝 Detailed form</h3>
      <select id="f-asset" class="field">${assetOptions()}</select>
      <input id="f-problem" class="field" placeholder="${esc(L().problem)} (short name)"><input id="f-symptom" class="field" placeholder="What you saw">
      <input id="f-cause" class="field" placeholder="Cause found"><input id="f-action" class="field" placeholder="What you did">
      <div class="row"><select id="f-outcome" class="field" style="max-width:200px"><option value="fixed">Worked</option><option value="failed_again">Didn't work</option><option value="temporary">Temporary</option><option value="open">Still open</option></select>
        <input id="f-min" class="field" type="number" placeholder="Minutes" style="max-width:120px"><button class="btn primary" id="f-go">Save</button></div><div id="f-out" class="small"></div></div>
  </div>`;
  $("#l-mic").onclick = (e) => toggleVoice(e.currentTarget, (t) => ($("#l-text").value = t));
  $("#lb-file").onchange = (e) => { const f = e.target.files[0]; if (f) logbookFlow($("#cap-out"), f); e.target.value = ""; };
  $("#vg-file").onchange = (e) => { const f = e.target.files[0]; if (f) videoFlow($("#cap-out"), f); e.target.value = ""; };
  $("#t-mic").onclick = (e) => toggleVoice(e.currentTarget, (t) => ($("#t-text").value = t));
  $("#l-go").onclick = async () => {
    $("#l-out").innerHTML = spin;
    try { const r = await api(`/api/i/${S.ind}/smart-log`, { json: { text: $("#l-text").value, person_id: S.person } }); const x = r.extracted || {};
      $("#l-out").innerHTML = `<div class="card" style="background:#fbf8f3"><b>✔ ${esc(r.message)}</b>
        <table class="t" style="margin-top:8px"><tr><td class="muted">${esc(L().asset)}</td><td><b>${esc(x.asset_id)}</b></td></tr><tr><td class="muted">${esc(L().problem)}</td><td>${esc(x.problem)}</td></tr>
        <tr><td class="muted">Cause</td><td>${esc(x.cause || "—")}</td></tr><tr><td class="muted">Action</td><td>${esc(x.action || "—")}</td></tr><tr><td class="muted">Result</td><td>${esc(OUTCOME[x.outcome] || x.outcome)}</td></tr>
        ${x.code ? `<tr><td class="muted">${esc(L().code)}</td><td class="mono">${esc(x.code)}</td></tr>` : ""}</table><p class="tiny muted eng-only">Saved to: ${esc(r.saved_to)}</p></div>`;
      guideHook("logged", r);
    } catch (e) { $("#l-out").innerHTML = `<span class="small" style="color:var(--bad)">${esc(e.message)}</span>`; }
  };
  $("#t-go").onclick = async () => {
    try { const r = await api(`/api/i/${S.ind}/tips`, { json: { person_id: S.person, asset_id: $("#t-asset").value, text: $("#t-text").value, source_ref: $("#t-src").value } }); $("#t-out").textContent = "✔ " + r.message; }
    catch (e) { $("#t-out").textContent = e.message; }
  };
  $("#f-go").onclick = async () => {
    try { const r = await api(`/api/i/${S.ind}/log`, { json: { asset_id: $("#f-asset").value, person_id: S.person, problem: $("#f-problem").value, symptom: $("#f-symptom").value, cause: $("#f-cause").value, action: $("#f-action").value, outcome: $("#f-outcome").value, downtime_minutes: +$("#f-min").value || 0 } });
      $("#f-out").textContent = "✔ " + r.message; } catch (e) { $("#f-out").textContent = e.message; }
  };
};

// ---------- memory browser ----------
VIEWS.memory = async (el) => {
  el.innerHTML = `<div class="panel-head"><div><h2>Memory</h2><p class="muted small">Everything Ustaad knows here, with how much to trust it.</p></div></div>
  <div class="card row"><input id="m-q" class="field" placeholder="Search…" style="flex:1;min-width:160px">
    <select id="m-kind" class="field" style="max-width:170px"><option value="">All kinds</option><option value="record">Team records</option><option value="tip">Expert tips</option><option value="manual">Maker's manual</option><option value="public">Public records</option></select>
    <select id="m-tier" class="field" style="max-width:170px"><option value="">All trust levels</option>${Object.keys(TIER).slice(0, 5).map((k) => `<option value="${k}">${TIER[k][1]}</option>`).join("")}</select>
    <select id="m-asset" class="field" style="max-width:220px"><option value="">All ${esc(L().assets.toLowerCase())}</option>${pack().assets.map((a) => `<option value="${a.id}">${esc(a.id)}</option>`).join("")}</select></div>
  <div id="m-sum" class="small muted" style="margin:10px 2px"></div><div id="m-list">${spin}</div>`;
  const d = await api(`/api/i/${S.ind}/memories`);
  const counts = {}; d.memories.forEach((m) => (counts[m.trust.tier] = (counts[m.trust.tier] || 0) + 1));
  const draw = () => {
    const q = $("#m-q").value.toLowerCase(), k = $("#m-kind").value, t = $("#m-tier").value, a = $("#m-asset").value;
    const list = d.memories.filter((m) => (!k || m.kind === k) && (!t || m.trust.tier === t) && (!a || m.asset_id === a) && (!q || m.text.toLowerCase().includes(q)));
    $("#m-sum").innerHTML = `${list.length} of ${d.total} memories · ` + Object.entries(counts).map(([k2, v]) => `${tierBadge(k2)} ${v}`).join(" ");
    $("#m-list").innerHTML = list.slice(0, 120).map(memCard).join("") || '<div class="empty">Nothing matches.</div>';
    bindMemButtons($("#m-list"));
  };
  $$("#m-q, #m-kind, #m-tier, #m-asset").forEach((x) => (x.oninput = draw)); draw();
};

// ---------- approvals ----------
VIEWS.approvals = async (el) => {
  const d = await api(`/api/i/${S.ind}/pending`); const r = roleObj();
  el.innerHTML = `<div class="panel-head"><div><h2>Approvals</h2><p class="muted small">New knowledge waits here until a senior checks it. Approved memories count as trusted.</p></div><span class="badge b-unreviewed">${d.pending.length} waiting</span></div>
  ${r.can_approve ? "" : '<div class="card small">Only a senior role can approve.</div>'}
  <div class="stack">${d.pending.map((x) => `<div class="card" data-k="${x.id}"><div class="row"><span class="badge b-unreviewed">Unreviewed</span><span class="badge b-src">${x.kind === "tip" ? "💡 Tip" : "📝 Record"}</span>
    <b>${esc(x.asset_id)}</b><span class="small muted">${esc(personName(x.person_id))} · ${fmtDate(x.datetime || x.date)}</span></div>
    <p style="margin:8px 0">${x.kind === "tip" ? esc(x.text) : `<b>${esc(x.problem)}</b> — ${esc(x.symptom)}<br><span class="small">Did: ${esc(x.action)} · Result: ${esc(OUTCOME[x.outcome] || x.outcome)}</span>`}</p>
    ${r.can_approve ? `<div class="row"><button class="btn ok sm" data-ok="1">Approve</button><button class="btn bad sm" data-ok="0">Reject</button></div>` : ""}</div>`).join("") || '<div class="card empty">Nothing waiting. 🎉</div>'}</div>`;
  $$("[data-ok]", el).forEach((b) => (b.onclick = async () => {
    const card = b.closest("[data-k]");
    try { const res = await api(`/api/i/${S.ind}/approve`, { json: { key: card.dataset.k, role: S.role, approver_id: S.person, ok: b.dataset.ok === "1" } });
      card.innerHTML = `<b>${esc(res.message)}</b>`; guideHook("approved"); } catch (e) { toast(esc(e.message), "alert"); }
  }));
};

// ---------- playbook / SOP ----------
VIEWS.playbook = async (el) => {
  el.innerHTML = `<div class="panel-head no-print"><div><h2>SOP / playbook</h2><p class="muted small">One standard card built from what actually worked — print it or save as PDF.</p></div></div>
  <div class="card row no-print"><select id="p-asset" class="field" style="max-width:320px">${assetOptions()}</select><select id="p-prob" class="field" style="max-width:320px"></select><button class="btn accent" id="p-go">Build SOP</button></div>
  <div id="p-out" style="margin-top:16px"></div>`;
  const loadProbs = async () => { const d = await api(`/api/i/${S.ind}/problems?asset_id=${$("#p-asset").value}`);
    $("#p-prob").innerHTML = d.problems.map((x) => `<option>${esc(x.problem)}</option>`).join("") || "<option value=''>No history yet</option>"; };
  $("#p-asset").onchange = loadProbs; await loadProbs();
  $("#p-go").onclick = async () => {
    $("#p-out").innerHTML = `<div class="card">${spin} Writing the SOP…</div>`;
    try { const c = await api(`/api/i/${S.ind}/playbook`, { json: { asset_id: $("#p-asset").value, problem: $("#p-prob").value, language: S.lang } });
      const li = (a) => (a || []).map((x) => `<li>${esc(x)}</li>`).join("");
      $("#p-out").innerHTML = `<div class="card"><div class="row" style="justify-content:space-between"><div><div class="tiny muted">${esc(c.org)} · SOP · ${esc(c.generated)}</div><h2>${esc(c.title)}</h2></div>
        <button class="btn no-print" onclick="window.print()">🖨 Print / Save PDF</button></div>
        <p><b>When to use:</b> ${esc(c.when_to_use)}</p>
        <div class="grid g2"><div><h3>Symptoms</h3><ul>${li(c.symptoms)}</ul><h3>First checks</h3><ul>${li(c.first_checks)}</ul></div>
        <div><h3>Steps</h3><ol>${li(c.steps)}</ol>${c.parts?.length ? `<h3>Parts</h3><ul>${li(c.parts)}</ul>` : ""}</div></div>
        ${c.do_not?.length ? `<h3>Do NOT</h3><ul class="avoid">${li(c.do_not)}</ul>` : ""}
        <p>🦺 ${esc(c.safety)} · ⏱ ${esc(c.typical_time)}</p>
        <h3>Proof — verified by</h3><ul class="small">${li(c.verified_by)}</ul>
        ${c.expert_tips_used?.length ? `<h3>Expert tips used</h3><ul class="small">${li(c.expert_tips_used)}</ul>` : ""}
        ${c.hindsight_insight ? `<div class="tipbox"><b>Hindsight reflect:</b> ${esc(c.hindsight_insight)}</div>` : ""}
        <p class="tiny muted">Based on ${c.based_on_records} records in Ustaad memory.</p></div>`;
      guideHook("sop");
    } catch (e) { $("#p-out").innerHTML = `<div class="card">${esc(e.message)}</div>`; }
  };
};

// ---------- risk radar ----------
VIEWS.risk = async (el) => {
  const d = await api(`/api/i/${S.ind}/risk`);
  el.innerHTML = `<div class="panel-head"><div><h2>Knowledge risk radar</h2><p class="muted small">What leaves the building when someone leaves.</p></div></div>
  <div class="grid g2">${d.retiring_experts.map((x) => `<div class="card" style="border-left:5px solid var(--bad)">
    <div class="row" style="justify-content:space-between"><h3 style="margin:0">${esc(x.name)}</h3><span class="badge b-high">Leaving ${fmtDate(x.retiring_on)}</span></div>
    <p><b style="font-size:26px;font-family:var(--serif)">${x.share_of_all_known_fixes}%</b> of all known fixes here were first solved by ${esc(x.name.split(" ")[0])}.<br>
    <span class="small">${x.fixes_owned} fixes · only ${x.captured} written down as tips.</span></p>
    ${x.only_in_their_head.length ? `<div class="small"><b>Only in their head:</b><ul>${x.only_in_their_head.map((y) => `<li>${esc(y)}</li>`).join("")}</ul></div>` : ""}
    <button class="btn accent sm" data-iv="${x.person_id}">🎤 Start exit interview</button></div>`).join("") || '<div class="card">No one is leaving soon.</div>'}</div>
  <div class="card scroll" style="margin-top:16px"><table class="t"><tr><th>${esc(L().asset)}</th><th>Risk</th><th>Known fixes</th><th>Top expert</th><th>Leaving share</th><th>Not written down</th></tr>
  ${d.assets.map((a) => `<tr><td><b>${esc(a.asset_id)}</b><div class="tiny muted">${esc(a.asset)}</div></td><td><span class="badge b-${a.level}">${a.level}</span></td><td>${a.families}</td>
    <td>${esc(a.top_owner)} (${a.top_owner_share}%)</td><td>${a.retiring_share}%</td><td class="small">${a.uncaptured.map((u) => esc(u.problem)).join(", ") || "—"}</td></tr>`).join("")}</table></div>`;
  $$("[data-iv]", el).forEach((b) => (b.onclick = () => { S.ivPerson = b.dataset.iv; go(`#/i/${S.ind}/${S.role}/interview`); }));
};

// ---------- interview ----------
VIEWS.interview = async (el) => {
  const leaving = pack().people.find((p) => p.retiring_on); const pid = S.ivPerson || leaving?.id || pack().people[0].id; S.ivPerson = null;
  el.innerHTML = `<div class="panel-head"><div><h2>Before-you-leave interview</h2><p class="muted small">Questions aimed only at knowledge that is not written down yet. Answer by voice — it becomes an expert tip.</p></div></div>
  <div class="card row"><select id="iv-p" class="field" style="max-width:360px">${personOptions(pid)}</select></div><div id="iv-out" style="margin-top:14px">${spin}</div>`;
  const load = async () => {
    const d = await api(`/api/i/${S.ind}/interview?person_id=${$("#iv-p").value}&language=${S.lang}`);
    $("#iv-out").innerHTML = `<p class="small">${esc(d.person.name)}: ${d.fixes_owned} fixes owned, ${d.captured} written down.</p>
    <div class="stack">${d.questions.map((q, i) => `<div class="card" data-i="${i}"><div class="row"><span class="badge ${q.priority === "high" ? "b-high" : "b-medium"}">${esc(q.priority)}</span><span class="badge b-src">${esc(q.asset_id)}</span></div>
      <p style="margin:8px 0"><b>${esc(q.question)}</b></p><p class="small muted">${esc(q.why)}</p>
      <textarea class="field" placeholder="${esc(d.person.short || d.person.name)}'s answer…"></textarea>
      <div class="row" style="margin-top:6px"><button class="iconbtn" data-mic>🎙️</button><button class="btn primary sm" data-save>Save as expert tip</button><span class="small" data-msg></span></div></div>`).join("")}</div>`;
    $$("[data-i]", $("#iv-out")).forEach((card) => {
      const q = d.questions[+card.dataset.i]; const ta = $("textarea", card);
      $("[data-mic]", card).onclick = (e) => toggleVoice(e.currentTarget, (t) => (ta.value = t));
      $("[data-save]", card).onclick = async () => {
        try { const r = await api(`/api/i/${S.ind}/interview/answer`, { json: { person_id: $("#iv-p").value, asset_id: q.asset_id, question: q.question, answer: ta.value } });
          $("[data-msg]", card).textContent = "✔ " + r.message; guideHook("interview"); } catch (e) { $("[data-msg]", card).textContent = e.message; }
      };
    });
  };
  $("#iv-p").onchange = load; await load();
};

// ---------- shift report ----------
VIEWS.shift = async (el) => {
  const brief = document.createElement("div"); brief.innerHTML = `<button class="btn accent" id="sh-brief">📢 Play the morning briefing</button><div id="sh-briefout" style="margin-top:8px"></div>`;
  el.innerHTML = `<div class="panel-head"><div><h2>Shift report</h2><p class="muted small">Built from real data: work records, sensor alerts, repeat failures and pending approvals.</p></div>
    <select id="sh-h" class="field" style="max-width:160px"><option value="24">Last 24 hours</option><option value="72">Last 3 days</option><option value="168">Last 7 days</option></select></div><div id="sh-out">${spin}</div>`;
  const load = async () => {
    const d = await api(`/api/i/${S.ind}/shift-report?hours=${$("#sh-h").value}&language=${S.lang}`);
    $("#sh-out").innerHTML = `<div class="card">${d.note ? `<p class="small muted">${esc(d.note)}</p>` : ""}<div style="white-space:pre-wrap;font-size:15px">${esc(d.summary)}</div></div>
    ${d.parts_out?.length ? `<div class="card" style="margin-top:14px"><h3>📦 Out of stock</h3><div class="row">${d.parts_out.map((x) => `<a class="badge b-failed" href="#/i/${S.ind}/${S.role}/machines/${x.asset_id}">${esc(x.part)} · ${esc(x.asset_id)}</a>`).join("")}</div></div>` : ""}
    ${d.events?.length ? `<div class="card scroll" style="margin-top:14px"><table class="t"><tr><th>Time</th><th>${esc(L().asset)}</th><th>${esc(L().problem)}</th><th>Result</th><th>By</th><th>Min</th></tr>
      ${d.events.map((e) => `<tr><td class="small">${esc(e.time)}</td><td><b>${esc(e.asset_id)}</b></td><td>${esc(e.problem)}</td><td>${e.outcome === "fixed" ? '<span class="badge b-verified">Worked</span>' : `<span class="badge b-failed">${esc(OUTCOME[e.outcome] || e.outcome)}</span>`}${e.status === "pending" ? ' <span class="badge b-unreviewed">Unreviewed</span>' : ""}</td><td>${esc(e.person)}</td><td>${Math.round(e.downtime_minutes || 0)}</td></tr>`).join("")}</table></div>` : ""}`;
  };
  $("#sh-h").onchange = load; await load();
  el.querySelector(".panel-head").after(brief); brief.style.marginBottom = "14px"; $("#sh-brief").onclick = () => playBriefing($("#sh-briefout"));
};

// ---------- skills ----------
VIEWS.skills = async (el) => {
  const d = await api(`/api/i/${S.ind}/skills`);
  const max = Math.max(1, ...Object.values(d.grid).flatMap((r) => Object.values(r)));
  const ppl = Object.fromEntries(pack().people.map((x) => [x.id, x]));
  const holders = (a) => d.people.filter((p) => d.grid[p.id][a] > 0).length;
  el.innerHTML = `<div class="card" style="margin-bottom:14px;border-top:4px solid var(--accent)"><h3>🔎 Who can fix this?</h3>
      <div class="row" style="flex-wrap:nowrap"><input class="field" id="xf-q" placeholder="e.g. hydraulic leak at Pune · alarm 2041 · fryer not heating"><button class="btn accent" id="xf-go">Find</button></div>
      <div class="tiny muted" style="margin-top:4px">Ranked by proof — fixes that worked and fixes others reused — not by job title.</div><div id="xf-out"></div></div>
  <div class="panel-head"><div><h2>Skills matrix</h2><p class="muted small">Who has proven fixes on which ${esc(L().asset.toLowerCase())}. Darker = more proven fixes. <span class="badge b-failed">⚠ 1 person</span> = only one person can fix it.</p></div></div>
  <div class="card scroll"><table class="t heat"><tr><th></th>${d.assets.map((a) => { const n = holders(a); return `<th class="mono ${n === 1 ? "solo" : ""}" title="${n} person(s) with proven fixes">${esc(a)}${n === 1 ? "<div class='tiny'>⚠ 1 person</div>" : n === 0 ? "<div class='tiny muted'>nobody yet</div>" : ""}</th>`; }).join("")}</tr>
  ${d.people.map((p) => `<tr><td><b>${esc(p.name)}</b><div class="tiny muted">${esc(p.role)}</div>${ppl[p.id]?.retiring_on ? `<span class="badge b-high">Leaving ${fmtDate(ppl[p.id].retiring_on)}</span>` : ""}</td>${d.assets.map((a) => { const v = d.grid[p.id][a];
    return `<td class="c ${v && holders(a) === 1 ? "solo-cell" : ""}" style="background:rgba(232,131,58,${v ? 0.15 + 0.75 * v / max : 0});color:${v / max > 0.6 ? "#fff" : "inherit"}">${v || ""}</td>`; }).join("")}</tr>`).join("")}</table></div>
  <p class="small muted">Red columns are the biggest risk: if that one person leaves, so does the fix. Use 🎤 Exit interview or 🎥 a fix video to capture it.</p>`;
  const find = async () => { const q = $("#xf-q").value.trim(); if (!q) return; $("#xf-out").innerHTML = spin;
    try { const r = await api(`/api/i/${S.ind}/experts?q=${encodeURIComponent(q)}`);
      $("#xf-out").innerHTML = r.experts.length ? `<div class="grid g3" style="margin-top:10px">${r.experts.map((x, i) => `<div class="card"><div class="tiny muted">#${i + 1}${r.site ? " · at " + esc(r.site) : ""}</div><h3 style="margin:2px 0">${esc(x.name)}</h3>
        <div class="small muted">${esc(x.role)}${x.site ? " · " + esc(x.site) : ""}</div>${x.leaving ? `<span class="badge b-high">Leaving ${fmtDate(x.leaving)}</span>` : ""}
        <div class="small" style="margin-top:6px"><b>${x.fixes}</b> matching fix(es) that worked</div>${x.proof.map((e) => `<div class="tiny muted">• ${fmtDate(e.date)} ${esc(e.asset_id)}: ${esc(e.action)}</div>`).join("")}
        <div class="row" style="margin-top:8px"><a class="btn ok sm" target="_blank" rel="noopener" href="https://wa.me/?text=${encodeURIComponent(x.message)}">💬 WhatsApp</a><button class="btn sm" data-askx="${x.id}">🧓 Ask ${esc(x.name.split(" ")[0])}'s memory</button></div></div>`).join("")}</div>`
        : `<p class="small muted" style="margin-top:8px">Nobody has a recorded fix for that yet${r.site ? " at " + esc(r.site) : ""}. That's a gap worth capturing.</p>`;
      $$("[data-askx]").forEach((b) => (b.onclick = () => { S.prefill = { expert_id: b.dataset.askx, problem: q }; go(`#/i/${S.ind}/${S.role}/ask`); }));
    } catch (e) { $("#xf-out").innerHTML = `<p class="small" style="color:var(--bad)">${esc(e.message)}</p>`; } };
  $("#xf-go").onclick = find; $("#xf-q").onkeydown = (e) => { if (e.key === "Enter") find(); };
};

// ---------- passport ----------
function skillGraph(d) {
  const sk = d.skills.slice(0, 10), W = 420, H = 300, cx = W / 2, cy = H / 2, R = 115;
  const col = { verified: "#15803d", attested: "#1d4ed8", self: "#9ca3af" };
  const nodes = sk.map((s, i) => { const ang = -Math.PI / 2 + 2 * Math.PI * i / Math.max(sk.length, 1); return { s, x: cx + R * Math.cos(ang), y: cy + R * Math.sin(ang), r: 7 + 4 * Math.min(s.fixes + s.confirmed_by_others, 5) }; });
  return `<svg viewBox="0 0 ${W} ${H}" class="skillgraph" role="img" aria-label="Skill graph">${nodes.map((n) => `<line x1="${cx}" y1="${cy}" x2="${n.x}" y2="${n.y}" stroke="#e5e7eb" stroke-width="${1 + n.s.fixes}"/>`).join("")}
    <circle cx="${cx}" cy="${cy}" r="30" fill="#16202e"/><text x="${cx}" y="${cy + 4}" text-anchor="middle" font-size="11" fill="#fff">${esc(d.person.name.split(" ")[0])}</text>
    ${nodes.map((n) => `<circle cx="${n.x}" cy="${n.y}" r="${n.r}" fill="${col[n.s.tier]}" opacity=".9"><title>${esc(n.s.skill)} — ${esc(n.s.label)}</title></circle>
      <text x="${n.x}" y="${n.y + n.r + 11}" text-anchor="middle" font-size="9" fill="#374151">${esc(n.s.skill.slice(0, 22))}</text>`).join("")}</svg>
    <div class="tiny muted" style="text-align:center">🟢 Verified · 🔵 Attested · ⚪ Self-declared · bigger = more proof</div>`;
}
function passportHTML(d, ind, pid) {
  return `<div class="passport"><div class="row" style="justify-content:space-between"><div><div class="seal">Ustaad · Skill passport</div><h2 style="margin:4px 0 0">${esc(d.person.name)}</h2>
    <div class="muted">${esc(d.person.role)} · ${esc(d.org)} · ${esc(d.industry)}</div>${d.private ? '<span class="badge b-src">🔒 Privacy mode: surname and company hidden</span>' : ""}</div>
    <div class="row no-print"><button class="btn sm" id="pp-share">🔗 Share link</button><button class="btn sm" id="pp-priv">🔒 Private link</button><button class="btn sm" onclick="window.print()">📄 Save as PDF</button>${d.private ? "" : `<button class="btn sm accent" id="pp-ask">🧓 Ask ${esc(d.person.name.split(" ")[0])}'s memory</button>`}</div></div>
  <div class="grid g4" style="margin:16px 0">
    <div class="kpi"><b>${d.totals.fixes}</b><span class="small muted">proven fixes</span></div><div class="kpi"><b>${d.totals.verified}</b><span class="small muted">verified skills</span></div>
    <div class="kpi"><b>${d.totals.reused_by_others}</b><span class="small muted">times others reused their fix</span></div><div class="kpi"><b>${d.totals.hours_saved}</b><span class="small muted">hours saved for others</span></div></div>
  <div class="grid g2"><div class="card">${skillGraph(d)}</div>
  <div class="card"><h3>What the proof levels mean</h3><p class="small"><span class="badge b-verified">✔ Verified</span> proven by 2+ independent confirmations — fixed it more than once, or a colleague reused the fix and it worked.</p>
    <p class="small"><span class="badge b-attested">Attested</span> proven once by a real fix.</p><p class="small"><span class="badge b-self">Self-declared</span> their own tip, not yet proven by a fix.</p>
    <p class="tiny muted">Built only from ${esc(d.org)} records in Ustaad — nobody can type their own skills in.</p></div></div>
  <table class="t" style="margin-top:14px"><tr><th>Skill</th><th>Proof level</th><th>Fixes</th><th>Confirmed by others</th><th>Proof</th></tr>
  ${d.skills.map((s) => `<tr><td><b>${esc(s.skill)}</b><div class="tiny muted mono">${esc(s.assets.join(", "))}</div></td><td>${{ verified: '<span class="badge b-verified">✔ Verified</span>', attested: '<span class="badge b-attested">Attested</span>', self: '<span class="badge b-self">Self-declared</span>' }[s.tier] || ""}<div class="tiny muted">${esc(s.label)}</div></td><td>${s.fixes}</td><td>${s.confirmed_by_others}</td>
    <td>${(s.evidence || []).length ? `<details><summary class="tiny">${s.evidence.length} record(s)</summary>${s.evidence.map((e) => `<div class="tiny">• ${fmtDate(e.date)} ${esc(e.asset_id)} — ${esc(e.action)} <i class="muted">(${esc(e.kind)}${e.approved_by ? ", approved by " + esc(e.approved_by) : ""})</i></div>`).join("")}</details>` : '<span class="tiny muted">tip</span>'}</td></tr>`).join("")}</table></div>`;
}
function bindPassport(d, ind, pid) {
  const base = `${location.origin}/p/${ind}/${pid}`;
  $("#pp-share").onclick = () => { navigator.clipboard?.writeText(base); toast("Link copied: " + esc(base)); };
  $("#pp-priv").onclick = () => { navigator.clipboard?.writeText(base + "?private=1"); toast("Private link copied — surname and company are hidden."); };
  if ($("#pp-ask")) $("#pp-ask").onclick = () => { S.prefill = { expert_id: pid }; go(`#/i/${ind}/${S.role || (pack().roles[0] || {}).id}/ask`); };
}
VIEWS.passport = async (el) => {
  el.innerHTML = `<div class="panel-head no-print"><div><h2>Skill passport</h2><p class="muted small">Credit for experts — proof of skill a worker can carry anywhere.</p></div>
    <select id="pp-p" class="field" style="max-width:360px">${personOptions(pack().people[0].id)}</select></div><div id="pp-out">${spin}</div>`;
  const load = async () => { const pid = $("#pp-p").value; const d = await api(`/api/i/${S.ind}/passport/${pid}`); $("#pp-out").innerHTML = passportHTML(d, S.ind, pid); bindPassport(d, S.ind, pid); };
  $("#pp-p").onchange = load; await load();
};
async function renderPassportPage(ind, pid, mode) {
  await loadPack(ind); const priv = mode === "private"; const d = await api(`/api/i/${ind}/passport/${pid}${priv ? "?private=1" : ""}`);
  app.innerHTML = `<div class="crumbs no-print"><a href="#/">Ustaad</a>${priv ? "" : ` › <a href="#/i/${ind}">${esc(pack().name)}</a>`} › Skill passport</div>${passportHTML(d, ind, pid)}`;
  bindPassport(d, ind, pid);
}

// ---------- stats ----------
VIEWS.stats = async (el) => {
  const [d, rep, cs, cna] = await Promise.all([api(`/api/i/${S.ind}/stats`), api(`/api/i/${S.ind}/repeat`), api(`/api/i/${S.ind}/cross-site`), api(`/api/i/${S.ind}/cost-of-not-asking`).catch(() => null)]);
  const b = d.before, a = d.after; const pct = (x, y) => (x ? Math.round(100 * (x - y) / x) : 0);
  const roi = d.roi || {};
  el.innerHTML = `<div class="panel-head"><div><h2>ROI dashboard</h2><p class="muted small">What Ustaad changed since it started (${fmtDate(d.ustaad_started)}).</p></div></div>
  <div class="grid g4 roi-tiles">
    <div class="kpi big"><span class="small muted">Downtime hours saved</span><b>${roi.hours_saved ?? 0} h</b><span class="tiny muted">faster fixes × problems since start</span></div>
    <div class="kpi big"><span class="small muted">Repeat failures avoided</span><b>${roi.repeat_failures_avoided ?? 0}</b><span class="tiny muted">failed fixes not repeated</span></div>
    <div class="kpi big"><span class="small muted">Fixed vs failed</span><b>${roi.fixed_rate ?? 0}% worked</b><span class="tiny muted">${roi.fixed ?? 0} worked · ${roi.failed ?? 0} didn't</span></div>
    <div class="kpi big" style="background:var(--ink);color:#fff"><span class="small" style="opacity:.8">₹ saved</span><b style="color:var(--accent)">${rupees(d.money_saved)}</b><span class="tiny" style="opacity:.75">lower cost per problem × problems since start</span></div></div>
  <h3 style="margin-top:18px">Before vs after</h3>
  <div class="grid g4">
    <div class="kpi"><span class="small muted">Avg time to fix</span><b>${b.mttr_minutes} → ${a.mttr_minutes} min</b><span class="delta">↓ ${pct(b.mttr_minutes, a.mttr_minutes)}%</span></div>
    <div class="kpi"><span class="small muted">Fixes that failed</span><b>${b.failed_fix_rate}% → ${a.failed_fix_rate}%</b><span class="delta">↓ ${b.failed_fix_rate - a.failed_fix_rate} pts</span></div>
    <div class="kpi"><span class="small muted">Avg cost per problem</span><b>${rupees(b.avg_cost)} → ${rupees(a.avg_cost)}</b><span class="delta">↓ ${pct(b.avg_cost, a.avg_cost)}%</span></div>
    <div class="kpi"><span class="small muted">Problems handled since start</span><b>${a.incidents}</b><span class="tiny muted">${d.records} records · ${d.tips} expert tips in memory</span></div></div>
  ${cna && cna.count ? costCard(cna, true) : ""}
  <div class="card" style="margin-top:14px"><h3>Month by month</h3><div id="st-c"></div></div>
  <div class="grid g2" style="margin-top:14px">
    <div class="card"><h3>🔁 Repeat problems</h3>${rep.repeat.map((r) => `<div style="padding:6px 0;border-bottom:1px solid #f1ece3"><b>${esc(r.asset_id)}</b> · ${esc(r.problem)} <span class="badge b-src">${r.times}×</span>
      <div class="small muted">Every ~${r.avg_gap_days} days${r.next_expected ? ` · next due <b>${fmtDate(r.next_expected)}</b>` : ""} · ${r.total_downtime_hours} h lost · ${rupees(r.total_cost)}</div></div>`).join("") || '<p class="small muted">No repeat pattern yet.</p>'}</div>
    <div class="card"><h3>🌐 Cross-site learning</h3>${cs.links.map((l) => `<div style="padding:6px 0;border-bottom:1px solid #f1ece3"><b>${esc(l.asset_id)}</b> <span class="small muted">(${esc(l.site)}, model ${esc(l.model)})</span>
      <div class="small">learns from: ${l.learns_from.map((x) => `${esc(x.problem)} — ${esc(x.person)}, ${esc(x.site)}`).join("; ")}</div></div>`).join("") || '<p class="small muted">Only one site.</p>'}</div></div>`;
  MC.combo($("#st-c"), { labels: d.monthly.map((m) => m.month), bars: d.monthly.map((m) => m.incidents), line: d.monthly.map((m) => m.mttr_minutes), barLabel: "Problems", lineLabel: "Avg minutes to fix" });
};

// ---------- knowledge coverage map ----------
VIEWS.coverage = async (el) => {
  const d = await api(`/api/i/${S.ind}/coverage`); const sm = d.summary; const sites = Object.fromEntries((pack().sites || []).map((x) => [x.id, x.name]));
  const col = { good: "var(--ok)", ok: "var(--warn)", low: "var(--bad)" };
  el.innerHTML = `<div class="panel-head"><div><h2>Knowledge coverage</h2><p class="muted small">Score out of 100: proven fixes for its problems, written-down tips, how many people can fix it, and its manual. Weakest first.</p></div></div>
  <div class="grid g4">
    <div class="kpi big"><span class="small muted">Average coverage</span><b>${sm.average}/100</b></div>
    <div class="kpi big"><span class="small muted">Only one person knows it</span><b style="color:var(--bad)">${sm.single_expert}</b><span class="tiny muted">of ${sm.machines} ${esc(L().assets.toLowerCase())}</span></div>
    <div class="kpi big"><span class="small muted">No maker's manual</span><b>${sm.no_manual}</b></div>
    <div class="kpi"><span class="small muted">What to do</span><span class="small">Run the exit interview for every 🚩 expert; add manuals in My ${esc(L().assets.toLowerCase())}.</span></div></div>
  <div class="grid g3" style="margin-top:14px">${d.machines.map((m) => `
    <a class="card mcard" href="#/i/${S.ind}/${S.role}/machines/${encodeURIComponent(m.asset_id)}" style="border-top:4px solid ${col[m.level]}">
      <div class="row" style="justify-content:space-between"><b class="mono">${esc(m.asset_id)}</b><b style="font-size:22px;color:${col[m.level]}">${m.score}<span class="tiny muted">/100</span></b></div>
      <div class="small">${esc(nm({ id: m.asset_id, name: m.asset }))}</div><div class="tiny muted">${esc(sites[m.site] || "")}</div>
      <div class="bar" style="height:6px;background:#eee;border-radius:4px;margin:8px 0"><div style="height:6px;border-radius:4px;width:${m.score}%;background:${col[m.level]}"></div></div>
      <div class="tiny">${m.proven}/${m.problem_types} problem types with a proven fix · ${m.written_down} written down · ${m.experts.length} expert(s)${m.manual_facts ? " · 📘 manual" : ""}</div>
      ${m.flags.length ? `<div style="margin-top:6px">${m.flags.map((f) => `<div class="tiny" style="color:var(--bad)">🚩 ${esc(f)}</div>`).join("")}</div>` : '<div class="tiny" style="color:var(--ok);margin-top:6px">✔ Well covered</div>'}
    </a>`).join("")}</div>`;
};

// ---------- expert leaderboard ----------
VIEWS.leaderboard = async (el) => {
  const d = await api(`/api/i/${S.ind}/leaderboard`); const medal = ["🥇", "🥈", "🥉"];
  el.innerHTML = `<div class="panel-head"><div><h2>Expert leaderboard</h2><p class="muted small">${esc(d.how)}</p></div></div>
  <div class="grid g3">${d.people.slice(0, 3).map((p, i) => `<div class="card" style="text-align:center"><div style="font-size:34px">${medal[i]}</div><h3 style="margin:4px 0">${esc(p.name)}</h3>
    <div class="tiny muted">${esc(p.role)}</div><div style="font-size:24px;font-weight:800;margin:6px 0">${p.points} pts</div>
    <div class="row" style="justify-content:center;gap:4px">${p.badges.map((b) => `<span class="badge b-verified">${esc(b)}</span>`).join("")}</div></div>`).join("")}</div>
  <div class="card" style="margin-top:14px;overflow-x:auto"><table class="t"><tr><th>#</th><th>Person</th><th>Fixes that worked</th><th>Success rate</th><th>Reused by others</th><th>Hours saved for others</th><th>Tips</th><th>Points</th></tr>
  ${d.people.map((p) => `<tr><td><b>${p.rank <= 3 ? medal[p.rank - 1] : p.rank}</b></td>
    <td><a href="#/passport/${S.ind}/${p.person_id}"><b>${esc(p.name)}</b></a> <span class="tiny muted">${esc(p.role)}</span>${p.leaving ? ` <span class="badge b-high">Leaving ${fmtDate(p.leaving)}</span>` : ""}
      <div>${p.badges.map((b) => `<span class="badge b-src">${esc(b)}</span>`).join(" ")}</div></td>
    <td>${p.worked}</td><td>${p.success_rate == null ? "—" : p.success_rate + "%"}</td><td>${p.reused_by_others}</td><td>${p.hours_saved_for_others} h</td><td>${p.tips}</td><td><b>${p.points}</b></td></tr>`).join("")}</table></div>`;
};

// ---------- quiz ----------
VIEWS.quiz = async (el) => {
  const pre = S.prefill || {}; S.prefill = null;
  const src = pre.quiz_asset || store.get("ustaad-quiz-src") || "team";
  let d;
  try { d = src === "team" ? await api(`/api/i/${S.ind}/quiz`) : await api(`/api/i/${S.ind}/machines/${encodeURIComponent(src)}/quiz`); }
  catch (e) { d = await api(`/api/i/${S.ind}/quiz`); toast(esc(e.message)); }
  let i = 0, score = 0;
  el.innerHTML = `<div class="card row" style="margin-bottom:12px"><b>🎓 Quiz from:</b><select id="qz-src" class="field" style="max-width:420px"><option value="team">The team's own past problems</option>
      <optgroup label="A machine's own manual">${pack().assets.map((a) => `<option value="${a.id}" ${a.id === src ? "selected" : ""}>${esc(a.id)} — ${esc(nm(a))}</option>`).join("")}</optgroup></select>
      ${d.asset ? `<span class="tiny muted">from ${esc(d.from)} — every answer has its page</span>` : ""}</div>
  <div class="panel-head"><div><h2>Onboarding quiz</h2><p class="muted small">New joiners learn from this team's own past problems — not generic manuals.</p></div><span id="qz-s" class="badge b-src"></span></div><div class="card" id="qz"></div>`;
  const draw = () => {
    $("#qz-s").textContent = `Score ${score}/${d.questions.length}`;
    if (i >= d.questions.length) { $("#qz").innerHTML = `<h3>Done! ${score}/${d.questions.length}</h3><p class="muted">Every question came from a real record in memory.</p><button class="btn" id="qz-r">Try again</button>`; $("#qz-r").onclick = () => VIEWS.quiz(el); return; }
    const q = d.questions[i];
    $("#qz").innerHTML = `<div class="tiny muted">Question ${i + 1} of ${d.questions.length}</div><h3>${esc(q.question)}</h3>${q.options.map((o, k) => `<button class="btn quiz-opt" data-k="${k}">${esc(o)}</button>`).join("")}<div id="qz-x"></div>`;
    $$(".quiz-opt").forEach((b) => (b.onclick = () => { const k = +b.dataset.k; if (k === q.answer) score++;
      $$(".quiz-opt").forEach((x) => { x.disabled = true; if (+x.dataset.k === q.answer) x.classList.add("right"); else if (x === b) x.classList.add("wrong"); });
      $("#qz-x").innerHTML = `<p class="small">${k === q.answer ? "✔ Right." : "✖ Not quite."} ${esc(q.explain)} ${d.asset && q.page ? pgLink(d.asset.id, q.page, "", "", "open page " + q.page) : ""}</p><button class="btn primary" id="qz-n">Next →</button>`; $("#qz-n").onclick = () => { i++; draw(); }; }));
  };
  draw();
  $("#qz-src").onchange = (e) => { store.set("ustaad-quiz-src", e.target.value); VIEWS.quiz(el); };
};

// ---------- panels (industry data) ----------
function renderPanels(el, ids) {
  const panels = (pack().panels || []).filter((p) => !ids || ids.includes(p.id));
  el.innerHTML = panels.map((p, k) => `<div class="card" style="margin-top:14px"><h3>${esc(p.title)}</h3><div id="pn-${k}"></div><p class="tiny muted">Source: ${esc(p.source || "")}</p></div>`).join("");
  panels.forEach((p, k) => {
    const box = $(`#pn-${k}`);
    if (p.type === "bar") MC.hbar(box, { labels: p.data.labels, values: p.data.values });
    else if (p.type === "stacked" && p.data) MC.stacked(box, { labels: p.data.months, series: p.data.series, colors: PALETTE });
    else if (p.type === "list") box.innerHTML = p.data.map((x) => `<div style="padding:6px 0;border-bottom:1px solid #f1ece3"><span class="badge ${x.critical ? "b-high" : "b-src"}">${x.critical ? "Critical" : "General"}</span> <b>${x.count}</b> · <span class="small">${esc(x.text)}</span></div>`).join("");
    else if (p.type === "logs") box.innerHTML = `<div class="scroll"><table class="t">${p.data.map((s) => `<tr><td><b>${esc(s.system)}</b></td><td>${s.top.map((t) => `<div class="mono" style="font-size:12px">${t.count}× ${esc(t.pattern)}</div>`).join("")}</td></tr>`).join("")}</table></div>`;
  });
}
async function publicSearch(el, placeholder, filterFn) {
  el.innerHTML = `<div class="card" style="margin-top:14px"><div class="row"><input class="field" id="ps-q" placeholder="${esc(placeholder)}" style="flex:1"></div><div id="ps-l" style="margin-top:10px">${spin}</div></div>`;
  const d = await api(`/api/i/${S.ind}/memories?kind=public`); let items = d.memories.filter(filterFn || (() => true));
  const draw = () => { const q = $("#ps-q").value.toLowerCase(); const l = items.filter((m) => !q || m.text.toLowerCase().includes(q));
    $("#ps-l").innerHTML = `<p class="small muted">${l.length} public records</p>` + l.slice(0, 40).map(memCard).join(""); bindMemButtons($("#ps-l")); };
  $("#ps-q").oninput = draw; draw();
}
VIEWS.dishes = async (el) => {
  const lk = pack().lookup;
  el.innerHTML = `<div class="panel-head"><div><h2>Customer & hygiene data</h2><p class="muted small">Real data behind the kitchen memories.</p></div></div><div id="pnl"></div>
  <div class="card" style="margin-top:14px"><h3>${esc(lk.title)}</h3><input class="field" id="dl-q" placeholder="Search a dish, e.g. biryani, dosa, rasgulla"><div id="dl-out" style="margin-top:8px"></div><p class="tiny muted">Source: ${esc(lk.source)}</p></div>`;
  renderPanels($("#pnl"));
  const draw = () => { const q = $("#dl-q").value.toLowerCase(); const l = lk.items.filter((x) => !q || (x.name + " " + x.ingredients).toLowerCase().includes(q)).slice(0, 12);
    $("#dl-out").innerHTML = `<table class="t"><tr><th>Dish</th><th>Ingredients</th><th>Prep</th><th>Cook</th><th>Region</th></tr>${l.map((x) => `<tr><td><b>${esc(x.name)}</b><div class="tiny muted">${esc(x.diet || "")} · ${esc(x.course || "")}</div></td><td class="small">${esc(x.ingredients)}</td><td>${x.prep_time ?? "—"}</td><td>${x.cook_time ?? "—"}</td><td class="small">${esc(x.state || "")}</td></tr>`).join("")}</table>`; };
  $("#dl-q").oninput = draw; draw();
};
VIEWS.devices = async (el) => {
  el.innerHTML = `<div class="panel-head"><div><h2>Device reports</h2><p class="muted small">Real FDA reports for ventilators and infusion pumps — many say what fixed the problem.</p></div></div><div id="pnl"></div><div id="ps"></div>`;
  renderPanels($("#pnl")); await publicSearch($("#ps"), "Search reports, e.g. battery, blower, filter, occlusion", (m) => (m.action || "").length > 3);
};
VIEWS.outages = async (el) => {
  el.innerHTML = `<div class="panel-head"><div><h2>Outage library</h2><p class="muted small">${pack().panels[0].title}. Ustaad uses these as outside evidence next to your team's own incidents.</p></div></div><div id="pnl"></div><div id="ps"></div>`;
  renderPanels($("#pnl")); await publicSearch($("#ps"), "Search outages, e.g. DNS, certificate, database, config");
};
VIEWS.obd = async (el) => {
  const lk = pack().lookup;
  el.innerHTML = `<div class="panel-head"><div><h2>OBD codes</h2><p class="muted small">What the code means (same for all cars) + what our mechanics found.</p></div></div>
  <div class="card"><div class="row"><input class="field mono" id="ob-q" placeholder="Type a code, e.g. P0171" style="max-width:220px"><button class="btn accent" id="ob-go">Look up</button></div><div id="ob-out" style="margin-top:10px"></div><p class="tiny muted">Source: ${esc(lk.source)}</p></div><div id="pnl"></div>`;
  renderPanels($("#pnl"));
  const mems = await api(`/api/i/${S.ind}/memories`);
  $("#ob-go").onclick = () => {
    const c = $("#ob-q").value.trim().toUpperCase(); const hit = lk.items.find((x) => x.code === c);
    const ours = mems.memories.filter((m) => m.kind !== "public" && m.text.toUpperCase().includes(c));
    $("#ob-out").innerHTML = `<h3 class="mono">${esc(c)}</h3><p>${hit ? `<b>${esc(hit.meaning)}</b>` : "Not in the generic list — may be a maker-specific code."}</p>
      ${ours.length ? `<h3>Our team's memory (${ours.length})</h3>${ours.map(memCard).join("")}` : '<p class="small muted">Our team has no memory of this code yet.</p>'}
      <button class="btn sm" id="ob-ask">💬 Ask Ustaad about ${esc(c)}</button>`;
    bindMemButtons($("#ob-out"));
    $("#ob-ask").onclick = () => { S.prefill = { asset_id: pack().assets[0].id, problem: `Check-engine light with code ${c}${hit ? " (" + hit.meaning + ")" : ""}`, auto: true }; go(`#/i/${S.ind}/${S.role}/ask`); };
  };
  $("#ob-q").onkeydown = (e) => { if (e.key === "Enter") $("#ob-go").click(); };
  $("#ob-q").value = "P0171"; $("#ob-go").click();
};
VIEWS.checklist = async (el) => {
  const cl = pack().checklists[0];
  el.innerHTML = `<div class="panel-head"><div><h2>${esc(cl.title)}</h2><p class="muted small">${esc(cl.source)}</p></div><button class="btn sm no-print" onclick="window.print()">🖨 Print</button></div>
  <div class="grid g3 checklist">${cl.phases.map((ph, k) => `<div class="phase"><h3>${esc(ph.name)}</h3><div class="tiny muted" data-prog="${k}"></div>
    ${ph.items.map((it) => `<label class="${it.startsWith("Neuro OT") ? "local" : ""}"><input type="checkbox" data-ph="${k}"><span>${esc(it)}</span></label>`).join("")}</div>`).join("")}</div>
  <p class="small muted">Lines in green are the demo hospital's own additions, learned from its incidents (e.g. navigation registration). Ustaad never gives clinical advice.</p>`;
  const upd = () => cl.phases.forEach((ph, k) => { const n = $$(`input[data-ph="${k}"]:checked`).length; $(`[data-prog="${k}"]`).textContent = `${n}/${ph.items.length} done${n === ph.items.length ? " ✔" : ""}`; });
  $$(".checklist input").forEach((c) => (c.onchange = upd)); upd();
};

// ---------- factory extras ----------
VIEWS.sensors = async (el) => {
  const d = await api("/api/factory/sensors"); const th = d.thresholds; const ids = Object.keys(d.series);
  el.innerHTML = `<div class="panel-head"><div><h2>Live sensors</h2><p class="muted small">Replay of the team's sensor file (every 15 min). Sensors say <i>something is wrong</i>; Ustaad says <i>what fixed it last time</i>.</p></div>
    <div class="row" style="flex-wrap:nowrap"><button class="btn" id="sn-bad" title="Sends one high reading for ${ids.includes("CNC-3") ? "CNC-3" : ids[0]} — the machine calls first">🚨 Test alert</button><button class="btn accent" id="sn-play">▶ Play</button><select id="sn-speed" class="field" style="max-width:120px"><option value="120">Fast</option><option value="300" selected>Normal</option><option value="700">Slow</option></select></div></div>
  <div class="grid g3" id="sn-now">${ids.map((a) => `<div class="kpi" data-a="${a}"><span class="small muted">${a}</span><b>— mm/s</b><span class="small">— °C · — kW</span></div>`).join("")}</div>
  <div class="card" style="margin-top:14px"><div class="sensor-legend">${ids.map((a, k) => `<span><i style="background:${PALETTE[k]}"></i>${a} vibration</span>`).join("")}<span><i style="background:#ca8a04"></i>${th.vib_warn} plan a stop</span><span><i style="background:#b91c1c"></i>${th.vib_stop} stop now</span></div>
    <div id="sn-c"></div><p class="tiny muted">${esc(th.why)} · ${esc(d.source)}</p></div>
  <div id="sn-alert"></div>`;
  const labels = d.series[ids[0]].map((p) => `${String(Math.floor(p.t / 60)).padStart(2, "0")}:${String(p.t % 60).padStart(2, "0")}`);
  const draw = (n) => MC.lines($("#sn-c"), { labels: labels.slice(0, Math.max(n, 2)), ymax: 10, ylabel: "vibration mm/s",
    series: ids.map((a, k) => ({ color: PALETTE[k], data: d.series[a].slice(0, n).map((p) => p.vib) })),
    hlines: [{ y: th.vib_warn, color: "#ca8a04" }, { y: th.vib_stop, color: "#b91c1c" }] });
  let i = 0, timer = null, alerted = false; draw(0);
  const step = () => {
    if (i >= labels.length) { clearInterval(timer); timer = null; $("#sn-play").textContent = "↺ Replay"; return; }
    draw(i + 1);
    ids.forEach((a) => { const p = d.series[a][i]; const k = $(`[data-a="${a}"]`); const bad = p.vib >= th.vib_warn || p.temp >= th.temp_warn;
      k.style.borderColor = p.vib >= th.vib_stop ? "var(--bad)" : bad ? "#ca8a04" : "var(--line)";
      k.innerHTML = `<span class="small muted">${a} · ${labels[i]}</span><b>${p.vib.toFixed(2)} mm/s</b><span class="small">${p.temp} °C · ${p.kw} kW</span>`;
      if (bad && !alerted) { alerted = true; showAlert(a, p); } });
    i++;
  };
  const showAlert = (a, p) => {
    toast(`⚠️ ${a}: vibration ${p.vib} mm/s, ${p.temp} °C`, "alert", 6000);
    const asset = pack().assets.find((x) => x.id === a);
    $("#sn-alert").innerHTML = `<div class="card" style="margin-top:14px;border-left:5px solid var(--bad)"><h3>⚠️ ${a} needs attention</h3>
      <p>Vibration <b>${p.vib} mm/s</b> and temperature <b>${p.temp} °C</b> — above this machine's normal. ${asset ? esc(asset.name) : ""}</p>
      <p class="small" id="sn-log">${spin} Writing the log by itself…</p>
      <div class="row"><button class="btn accent" id="sn-ask">💬 Ask Ustaad what fixed this before</button><a class="btn sm" href="#/i/${S.ind}/${S.role}/machines/${a}">🏭 Open ${a}'s page</a></div></div>`;
    api(`/api/i/${S.ind}/sensors/alert`, { json: { asset_id: a, reading: { vib: p.vib, temp: p.temp, time: labels[i] } } })
      .then((r) => { const el2 = $("#sn-log"); if (el2) el2.innerHTML = `📝 <b>${esc(r.message)}</b> When the technician taps <i>Worked</i>, this log is finished automatically.`; alertBar(); })
      .catch((e) => { const el2 = $("#sn-log"); if (el2) el2.textContent = e.message; });
    $("#sn-ask").onclick = () => { S.prefill = { asset_id: a, problem: `${a} spindle vibration rising to ${p.vib} mm/s and temperature ${p.temp} °C`, auto: true }; go(`#/i/${S.ind}/${S.role}/ask`); };
    guideHook("alert");
  };
  $("#sn-bad").onclick = async () => {
    const a = ids.includes("CNC-3") ? "CNC-3" : ids[0];
    try { const r = await api(`/api/i/${S.ind}/sensors/reading`, { json: { asset_id: a, vib: +(th.vib_stop + 0.6).toFixed(1), temp: 52 } });
      toast(r.alert ? `🚨 ${a} called. ${r.alert.message}` : "Reading sent — normal.", r.alert ? "alert" : "", 6000); alertBar(); window.scrollTo({ top: 0, behavior: "smooth" }); }
    catch (e) { toast(e.message, "alert"); }
  };
  $("#sn-play").onclick = () => {
    if (timer) { clearInterval(timer); timer = null; $("#sn-play").textContent = "▶ Play"; return; }
    if (i >= labels.length) { i = 0; alerted = false; draw(0); $("#sn-alert").innerHTML = ""; }
    timer = setInterval(step, +$("#sn-speed").value); $("#sn-play").textContent = "⏸ Pause";
  };
  S.charts.push({ destroy: () => clearInterval(timer) });
};
VIEWS.fleet = async (el) => {
  const d = await api("/api/factory/fleet"); const m = d.model_card;
  el.innerHTML = `<div class="panel-head"><div><h2>Failure prediction</h2><p class="muted small">${esc(m.question)} Trained on the public Microsoft Azure dataset: ${d.totals.machines} machines, ${d.totals.telemetry_rows.toLocaleString("en-IN")} sensor readings.</p></div></div>
  <div class="grid g4"><div class="kpi"><span class="small muted">Test AUC (Sep–Dec)</span><b>${m.test_auc}</b></div><div class="kpi"><span class="small muted">Failures caught in top 5% alerts</span><b>${Math.round(m.recall_top5pct * 100)}%</b></div>
    <div class="kpi"><span class="small muted">Alerts that were real</span><b>${Math.round(m.precision_top5pct * 100)}%</b></div><div class="kpi"><span class="small muted">Normal failure rate</span><b>${(m.base_failure_rate * 100).toFixed(1)}%</b></div></div>
  <div class="tipbox" style="margin-top:12px">⚖️ <b>Honest note:</b> Microsoft generated this dataset for a tutorial, so failure signals are much cleaner than in a real plant — expect lower accuracy on real data. We checked for data leakage (none found). The model says <i>when</i>; Ustaad's memory says <i>what to do</i>.</div>
  <div class="card scroll" style="margin-top:14px"><h3>Riskiest machines on ${fmtDate(d.demo_day)} (a test day)</h3><table class="t"><tr><th>Machine</th><th>Risk (24 h)</th><th>Why</th><th>What really happened</th></tr>
  ${d.fleet.slice(0, 14).map((f) => `<tr><td class="mono"><b>${esc(f.machine)}</b><div class="tiny muted">${esc(f.model)} · ${f.age_years} yrs</div></td><td><span class="badge ${f.risk > 0.5 ? "b-high" : f.risk > 0.1 ? "b-medium" : "b-low"}">${Math.min(99, Math.round(f.risk * 100))}%</span></td>
    <td class="small">${f.drivers.map(esc).join("<br>") || "—"}</td><td class="small">${f.actually_failed_next_24h ? `<span class="badge b-failed">Failed: ${esc(f.failed_component)}</span>` : '<span class="badge b-verified">No failure</span>'}</td></tr>`).join("")}</table></div>
  <div id="pnl"></div>`;
  renderPanels($("#pnl"), ["fleet-failures"]);
};
VIEWS.check = async (el) => {
  const d = await api("/api/factory/ai4i"); const t = d.typical;
  el.innerHTML = `<div class="panel-head"><div><h2>Failure check</h2><p class="muted small">Enter the machining settings. Rules learned from ${d.runs.toLocaleString("en-IN")} public runs (${d.failures} failures).</p></div></div>
  <div class="card grid g3">
    <div><label class="f">Product quality</label><select id="ck-type" class="field"><option value="L">L (low)</option><option value="M">M (medium)</option><option value="H">H (high)</option></select></div>
    <div><label class="f">Air temperature (K)</label><input id="ck-air" class="field" type="number" step="0.1" value="${t.air_K}"></div>
    <div><label class="f">Process temperature (K)</label><input id="ck-proc" class="field" type="number" step="0.1" value="${t.process_K}"></div>
    <div><label class="f">Spindle speed (rpm)</label><input id="ck-rpm" class="field" type="number" value="${t.rpm}"></div>
    <div><label class="f">Torque (Nm)</label><input id="ck-tq" class="field" type="number" step="0.1" value="${t.torque}"></div>
    <div><label class="f">Tool wear (min)</label><input id="ck-w" class="field" type="number" value="${t.tool_wear}"></div></div>
  <div id="ck-out" style="margin-top:14px"></div><p class="tiny muted">Source: ${esc(d.source)}</p>`;
  const run = () => {
    const ty = $("#ck-type").value, air = +$("#ck-air").value, proc = +$("#ck-proc").value, rpm = +$("#ck-rpm").value, tq = +$("#ck-tq").value, w = +$("#ck-w").value;
    const power = tq * rpm * 2 * Math.PI / 60, strain = w * tq, lim = { L: 11000, M: 12000, H: 13000 }[ty];
    const hits = { TWF: w >= 200, HDF: proc - air < 8.6 && rpm < 1380, PWF: power < 3500 || power > 9000, OSF: strain > lim };
    $("#ck-out").innerHTML = `<div class="grid g2">${d.modes.filter((m) => m.id !== "RNF").map((m) => `<div class="card" style="border-left:5px solid ${hits[m.id] ? "var(--bad)" : "var(--ok)"}">
      <div class="row" style="justify-content:space-between"><b>${esc(m.name)}</b>${hits[m.id] ? '<span class="badge b-high">RISK</span>' : '<span class="badge b-low">OK</span>'}</div>
      <p class="small">${esc(m.rule)}</p><p class="tiny muted">${m.count} such failures in the data.${m.id === "PWF" ? ` Now: ${Math.round(power)} W.` : m.id === "OSF" ? ` Now: ${Math.round(strain)} (limit ${lim}).` : m.id === "HDF" ? ` Now: ΔT ${(proc - air).toFixed(1)} K.` : ""}</p></div>`).join("")}</div>`;
  };
  $$("#tool input, #tool select").forEach((x) => (x.oninput = run)); run();
};

// ---------- My machines ----------
const HEALTH = { green: ["🟢", "Healthy"], amber: ["🟠", "Needs attention"], red: ["🔴", "Problem now"] };
VIEWS.machines = async (el, sub) => {
  if (sub === "accuracy") return benchView(el);
  if (sub) return machineProfile(el, decodeURIComponent(sub));
  const d = await api(`/api/i/${S.ind}/machines`); const canEdit = roleObj().can_approve; const p = pack();
  const bySite = {}; d.machines.forEach((m) => (bySite[m.site] = bySite[m.site] || []).push(m));
  el.innerHTML = `<div class="panel-head"><div><h2>My ${esc(L().assets.toLowerCase())}</h2><p class="muted small">Tap one to see everything about it.</p></div>
    <div class="row"><a class="btn" href="#/i/${S.ind}/${S.role}/machines/accuracy">📏 Reader accuracy</a>${canEdit ? `<button class="btn accent" id="mc-add">＋ Add ${esc(L().asset.toLowerCase())}</button>` : '<span class="small muted">Seniors can add new ones.</span>'}</div></div>
    <div id="mc-form"></div>
    ${p.sites.map((st) => (bySite[st.id] || []).length ? `<h3 style="margin-top:14px">📍 ${esc(st.name)}</h3><div class="grid g3">${bySite[st.id].map((m) => `
      <a class="card mcard" href="#/i/${S.ind}/${S.role}/machines/${encodeURIComponent(m.id)}">
        <div class="row" style="justify-content:space-between"><b class="mono" style="font-size:15px">${esc(m.id)}</b><span title="${esc(m.health.reasons.join(" · "))}">${HEALTH[m.health.level][0]} <span class="small">${HEALTH[m.health.level][1]}</span></span></div>
        <div>${esc(nm(m))}${m.custom ? ' <span class="badge b-tested">New</span>' : ""}</div><div class="tiny muted">${esc([m.maker, m.model].filter(Boolean).join(" · "))}</div>
        <div class="row" style="gap:6px;margin-top:6px"><span class="badge b-src">${m.fixed}/${m.problems} fixed</span>${m.due_soon ? `<span class="badge b-unreviewed">🔧 ${m.due_soon} due</span>` : ""}${m.parts_low ? `<span class="badge b-failed">📦 ${m.parts_low} low</span>` : ""}${m.manual ? `<span class="badge b-manual">📘 manual</span>` : ""}</div></a>`).join("")}</div>` : "").join("")}`;
  if ($("#mc-add")) $("#mc-add").onclick = () => machineForm($("#mc-form"));
};

const SPEC_DOT = { verified: ["🟢", "Checked: found in the source"], converted: ["🟢", "Checked, unit converted"], edited: ["✏️", "Typed by a person"],
  unverified: ["🟠", "Not found word-for-word in the source — check it"], suspicious: ["🔴", "Looks wrong — outside the normal range"], missing: ["⚪", "Not in the source"] };
function specGrid(fields, editable, aid) {
  return `<div class="sf-grid">${fields.map((f, i) => { const dot = SPEC_DOT[f.status] || SPEC_DOT.missing; const shown = f.shown ?? f.value ?? "";
    return `<div class="sf ${f.status || "missing"}" data-i="${i}"><div class="sf-l"><span title="${esc(dot[1])}">${dot[0]}</span> ${esc(f.label)}${f.unit && f.unit !== "count" ? ` <span class="tiny muted">(${esc(f.unit)})</span>` : ""}</div>
      ${editable ? `<input class="field sf-v" data-k="${esc(f.key)}" value="${esc(f.value || "")}" placeholder="—">` : `<div class="sf-v small"><b>${esc(shown || "—")}</b></div>`}
      ${f.value ? `<div class="tiny muted sf-q">${editable && f.std != null && String(f.note || "").startsWith("converted") ? `= ${esc(shown)}<br>` : ""}${f.quote ? `“${esc(f.quote)}”` : ""}${f.where ? ` — ${aid && /page (\d+)/.test(f.where) ? pgLink(aid, +f.where.match(/page (\d+)/)[1], "", f.quote || "", f.where) : esc(f.where)}` : ""}${f.note && !String(f.note).startsWith("converted") ? `<br>⚠️ ${esc(f.note)}` : ""}</div>` : ""}</div>`; }).join("")}</div>`;
}
function readPanel(d) {
  const r = d.read || {}; const c = d.spec_counts || {};
  const src = (r.sources || []).map((x) => `<li>${x.kind === "pdf" ? "📄" : x.kind === "web" ? "🌐" : x.kind === "photo" ? "📷" : "📝"} ${esc(String(x.ref || "").slice(0, 90))}${x.total_pages ? ` — ${x.total_pages} pages, used ${(x.kept_pages || []).length}` : ""}${(x.ocr_pages || []).length ? `, read ${x.ocr_pages.length} picture page(s) with Sarvam Vision` : ""}${(x.vision_pages || []).length ? `, read ${x.vision_pages.length} picture page(s) with the backup vision AI` : ""}${x.note ? ` <span class="muted">(${esc(x.note)})</span>` : ""}</li>`).join("");
  return `<div class="card readp"><div class="row" style="justify-content:space-between;align-items:flex-start"><div><b>🔎 What I read</b>
      <ul class="small" style="margin:4px 0 0 18px;padding:0">${src}</ul>
      ${(r.notes || []).length ? `<div class="tiny muted" style="margin-top:4px">${r.notes.map(esc).join("<br>")}</div>` : ""}
      <div class="small" style="margin-top:6px">Found <b>${r.rows_found || 0}</b> exact table rows${r.parts ? `, <b>${r.parts}</b> part numbers` : ""}. Type: <b>${esc(d.template_label || "General")}</b>.</div></div>
      ${d.image ? `<img src="${esc(d.image)}" alt="" style="max-width:110px;max-height:90px;border-radius:8px" onerror="this.remove()">` : ""}</div>
    ${(d.models || []).length > 1 ? `<div class="row" style="margin-top:8px;background:#fff7e6;padding:8px;border-radius:8px"><b class="small">This covers ${d.models.length} models. Which one is yours?</b>
      <select class="field" id="mf-pick" style="max-width:220px"><option value="">— pick —</option>${d.models.map((m) => `<option ${m === d.chosen_model ? "selected" : ""}>${esc(m)}</option>`).join("")}</select>
      <button class="btn sm accent" id="mf-pick-go">Fill for this model</button></div>` : ""}
    <div class="small" style="margin-top:8px">🟢 ${(c.verified || 0) + (c.converted || 0)} checked · 🟠 ${c.unverified || 0} to check · 🔴 ${c.suspicious || 0} look wrong · ⚪ ${c.missing || 0} not in the source
      ${d.spec_score != null && (c.verified + c.converted + c.unverified + c.suspicious) ? ` — <b>${d.spec_score}%</b> of filled values found word-for-word in the source` : ""}</div></div>`;
}

function machineForm(box, existing) {
  const p = pack(); const e = existing || {};
  const lines = (arr, f) => (arr || []).map(f).join("\n");
  box.innerHTML = `<div class="card stack" style="margin-bottom:16px;border-top:4px solid var(--accent)">
    <h3>${existing ? "Edit " + esc(e.id) : "Add a new " + esc(L().asset.toLowerCase())}</h3>
    <div><b>1 · Let Ustaad read it</b> <span class="small muted">— any manual, datasheet, product page or nameplate. Or skip and type.</span>
      <div class="grid g3" style="margin-top:8px">
        <div class="card src"><b>📄 PDF manual / datasheet</b><span class="tiny muted">Any size. Ustaad keeps the useful pages and reads tables, part lists and scanned pages.</span>
          <input type="file" id="mf-pdf" accept="application/pdf"><input class="field" id="mf-pages" placeholder="Pages with specs (optional), e.g. 40-45, 161"></div>
        <div class="card src"><b>🌐 Any web link</b><span class="tiny muted">Product page, brochure or PDF link. Ustaad also opens the datasheets it links to.</span><div class="row" style="flex-wrap:nowrap"><input class="field" id="mf-url" placeholder="https://…"><button class="btn sm" id="mf-url-go">Read</button></div></div>
        <label class="card src"><b>📷 Nameplate photo</b><span class="tiny muted">Snap the metal label on the machine.</span><input type="file" id="mf-photo" accept="image/*" capture="environment"></label>
      </div><div id="mf-status" class="small" style="margin-top:6px"></div><div id="mf-read"></div></div>
    <b>2 · Check and save</b>
    <div class="grid g3">
      <div><label class="f">ID (short)</label><input class="field mono" id="mf-id" value="${esc(e.id || "")}" ${existing ? "disabled" : ""} placeholder="e.g. CNC-4"></div>
      <div><label class="f">Name</label><input class="field" id="mf-name" value="${esc(e.name || "")}"></div>
      <div><label class="f">Site</label><select class="field" id="mf-site">${p.sites.map((st) => `<option value="${st.id}" ${st.id === e.site ? "selected" : ""}>${esc(st.name)}</option>`).join("")}</select></div>
      <div><label class="f">Maker</label><input class="field" id="mf-maker" value="${esc(e.maker || "")}"></div>
      <div><label class="f">Model</label><input class="field" id="mf-model" value="${esc(e.model || "")}"></div>
      <div><label class="f">Type</label><input class="field" id="mf-type" value="${esc(e.type || "")}"></div>
      <div><label class="f">Installed on</label><input class="field" type="date" id="mf-install" value="${esc(e.install_date || "")}"></div>
      <div><label class="f">Warranty until</label><input class="field" type="date" id="mf-warranty" value="${esc(e.warranty_until || "")}"></div>
      <div><label class="f">Service vendor</label><input class="field" id="mf-vendor" value="${esc(e.vendor || "")}" placeholder="Name"></div>
    </div>
    <div id="mf-fields">${(e.spec_fields || []).length ? `<label class="f">Key specs <span class="muted small">— tap a value to fix it</span></label>${specGrid(e.spec_fields, true)}` : ""}</div>
    <div class="grid g2">
      <div><label class="f">Other specs <span class="muted small">— one per line: label: value</span></label><textarea class="field mono" id="mf-specs" style="min-height:110px">${esc(lines((e.specs || []).filter((x) => !(e.spec_fields || []).some((f) => f.label === x.label)), (x) => `${x.label}: ${x.value}`))}</textarea></div>
      <div><label class="f">Parts <span class="muted small">— name | part no | replace every N days | in store</span></label><textarea class="field mono" id="mf-parts" style="min-height:110px">${esc(lines(e.components, (c) => `${c.name} | ${c.part_no || ""} | ${c.every_days || ""} | ${c.stock ?? ""}`))}</textarea></div>
    </div>
    <div id="mf-extra"></div>
    <div class="row"><button class="btn accent" id="mf-save">Save ${existing ? "changes" : ""}</button><button class="btn ghost" id="mf-cancel">Cancel</button><span id="mf-out" class="small"></span></div></div>`;
  let draft = { faults: [], service: [], source_ref: "", summary: e.summary || "", spec_fields: e.spec_fields || [], template: e.template || "" };
  const fill = (d) => {
    draft = d; const set = (id, v, force) => { if (v && (force || !$(id).value)) $(id).value = v; };
    set("#mf-name", d.name); set("#mf-maker", d.maker); set("#mf-model", d.chosen_model || d.model, !!d.chosen_model); set("#mf-type", d.template_label && d.template !== "general" ? d.template_label : d.type);
    if (!$("#mf-id").value && d.name) $("#mf-id").value = (L().asset.slice(0, 3) + "-" + Math.floor(Math.random() * 90 + 10)).toUpperCase().replace(/[^A-Z0-9-]/g, "");
    $("#mf-read").innerHTML = d.read ? readPanel(d) : "";
    if ((d.spec_fields || []).length) $("#mf-fields").innerHTML = `<label class="f">Key specs for a ${esc((d.template_label || "machine").toLowerCase())} <span class="muted small">— tap a value to fix it; 🟠/🔴 need a look</span></label>${specGrid(d.spec_fields, true)}`;
    const extra = (d.spec_extra || []).map((x) => `${x.label}: ${x.value}`);
    const old = (d.specs || []).filter((x) => !(d.spec_fields || []).some((f) => f.label === x.label)).map((x) => `${x.label}: ${x.value}`);
    if (extra.length || old.length) $("#mf-specs").value = [...new Set([...extra, ...old])].join("\n");
    const parts = [...(d.components || []).map((c) => `${c.name} | ${c.part_no || ""} | ${c.every_days || ""} | `)];
    (d.parts_found || []).forEach((x) => { if (!parts.some((l) => l.includes(x.part_no))) parts.push(`${x.name} | ${x.part_no} |  | `); });
    if (parts.length) $("#mf-parts").value = parts.slice(0, 30).join("\n");
    $("#mf-extra").innerHTML = `<div class="card" style="background:#f7f5ff"><b>📘 From the documents — saved into memory when you save:</b>
      ${d.summary ? `<p class="small">${esc(d.summary)}</p>` : ""}
      ${d.faults?.length ? `<div class="small"><b>${d.faults.length} known faults:</b> ${d.faults.map((f) => esc(f.title + (f.code ? ` (${f.code})` : ""))).join(" · ")}</div>` : ""}
      ${d.service?.length ? `<div class="small" style="margin-top:4px"><b>${d.service.length} service tasks:</b> ${d.service.map((x) => esc(x.task) + (x.every_days ? ` (every ${x.every_days} d)` : "")).join(" · ")}</div>` : ""}
      ${d.parts_found?.length ? `<div class="small" style="margin-top:4px"><b>${d.parts_found.length} part numbers</b> from the parts list (added to Parts).</div>` : ""}
      ${d.warranty_months ? `<div class="small" style="margin-top:4px"><b>Warranty:</b> ${d.warranty_months} months from install date</div>` : ""}
      ${d.note ? `<p class="tiny muted">${esc(d.note)}</p>` : ""}<p class="tiny muted">Source: ${esc(d.source_ref)}</p></div>`;
    $("#mf-status").innerHTML = (d.models || []).length > 1 && !d.chosen_model ? "✔ Read it. Pick your model below so the numbers are for your exact machine." : "✔ Read it. Check the coloured fields, give it an ID, then save.";
    if ($("#mf-pick-go")) $("#mf-pick-go").onclick = () => { const m = $("#mf-pick").value; if (!m) return toast("Pick a model first", "alert");
      read({ json: { read_id: d.read_id, model: m } }, `specs for ${m}`); };
  };
  const read = async (opts, what) => {
    $("#mf-status").innerHTML = `${spin} Reading the ${esc(what)}… (a big manual takes 20–40 seconds: identify → extract → check)`;
    try { fill(await api(`/api/i/${S.ind}/machines/read`, opts)); } catch (err) { $("#mf-status").innerHTML = `<span style="color:var(--bad)">${esc(err.message)}</span>`; }
  };
  const up = (inp, what) => { const f = inp.files[0]; if (!f) return; const fd = new FormData(); fd.append("file", f); if ($("#mf-pages").value.trim()) fd.append("pages", $("#mf-pages").value.trim()); read({ method: "POST", body: fd }, what); };
  $("#mf-pdf").onchange = (ev) => up(ev.target, "document"); $("#mf-photo").onchange = (ev) => up(ev.target, "nameplate");
  $("#mf-url-go").onclick = () => read({ json: { url: $("#mf-url").value, pages: $("#mf-pages").value } }, "link");
  $("#mf-cancel").onclick = () => { box.innerHTML = ""; };
  $("#mf-save").onclick = async () => {
    const spec_fields = (draft.spec_fields || []).map((f) => { const inp = $(`#mf-fields .sf-v[data-k="${CSS.escape(f.key)}"]`); const v = inp ? inp.value.trim() : f.value;
      return v === (f.value || "") ? f : { ...f, value: v, status: v ? "edited" : "missing", quote: "", where: v ? "typed by a person" : "", std: null, note: "" }; });
    const specs = [...spec_fields.filter((f) => f.value).map((f) => ({ label: f.label, value: f.status === "edited" ? f.value : (f.shown || f.value) })),
      ...$("#mf-specs").value.split("\n").map((l) => l.split(/:(.+)/)).filter((x) => x[0]?.trim() && x[1]?.trim()).map((x) => ({ label: x[0].trim(), value: x[1].trim() }))];
    const components = $("#mf-parts").value.split("\n").map((l) => l.split("|").map((x) => x.trim())).filter((x) => x[0])
      .map((x) => ({ name: x[0], part_no: x[1] || "", every_days: +x[2] || null, stock: x[3] === "" || x[3] === undefined ? null : +x[3] }));
    const m = { id: existing ? e.id : $("#mf-id").value, is_new: !existing, name: $("#mf-name").value, site: $("#mf-site").value, maker: $("#mf-maker").value,
      model: $("#mf-model").value, type: $("#mf-type").value, install_date: $("#mf-install").value, warranty_until: $("#mf-warranty").value,
      warranty_months: draft.warranty_months, vendor: $("#mf-vendor").value, specs, components, faults: draft.faults || [], service: draft.service || [],
      summary: draft.summary, source_ref: draft.source_ref || e.source_ref || "", spec_fields, template: draft.template || e.template || "",
      read_id: draft.read_id || "", image: draft.image || e.image || "", parts_found: draft.parts_found || [] };
    $("#mf-save").disabled = true;
    try { const r = await api(`/api/i/${S.ind}/machines`, { json: { machine: m, person_id: S.person, role: S.role } });
      delete S.packs[S.ind]; await loadPack(S.ind); toast(esc(r.message)); guideHook("machine"); go(`#/i/${S.ind}/${S.role}/machines/${encodeURIComponent(r.asset.id)}`); }
    catch (err) { $("#mf-out").innerHTML = `<span style="color:var(--bad)">${esc(err.message)}</span>`; $("#mf-save").disabled = false; }
  };
}

async function machineProfile(el, aid) {
  const d = await api(`/api/i/${S.ind}/machines/${encodeURIComponent(aid)}`); const a = d.asset; const canEdit = roleObj().can_approve;
  const qrUrl = `${location.origin}/m/${S.ind}/${encodeURIComponent(a.id)}`;
  const qrImg = `https://api.qrserver.com/v1/create-qr-code/?size=220x220&margin=6&data=${encodeURIComponent(qrUrl)}`;
  const h = HEALTH[d.health.level];
  el.innerHTML = `<div class="crumbs no-print"><a href="#/i/${S.ind}/${S.role}/machines">← All ${esc(L().assets.toLowerCase())}</a></div>
  <div class="card mhead"><div><div class="tiny muted">${esc(d.site)}${a.demo ? ' · <span class="badge b-src">dates & stock are demo data</span>' : ""}</div>
      <h2 style="margin:2px 0"><span class="mono">${esc(a.id)}</span> · ${esc(nm(a))}</h2>
      <div class="small muted">${esc([a.maker, a.model && "model " + a.model, a.type].filter(Boolean).join(" · "))}</div>
      ${a.summary ? `<p class="small" style="margin:6px 0 0">${esc(a.summary)}</p>` : ""}</div>
    <div class="health ${d.health.level}"><b>${h[0]} ${h[1]}</b><div class="tiny">${d.health.reasons.map(esc).join("<br>")}</div></div></div>
  <div class="row no-print" style="margin:12px 0"><a class="btn sm eng-only" href="/machines/${S.ind}/${encodeURIComponent(a.id)}.md" target="_blank" title="This machine as a Markdown file, for people and other AIs">🤖 .md</a><button class="btn accent" id="mp-ask">💬 Ask about ${esc(a.id)}</button><button class="btn" id="mp-log">✍️ I fixed something</button>${canEdit ? '<button class="btn" id="mp-edit">✏️ Edit details</button>' : ""}</div>
  <div id="mp-form"></div>
  <div class="tabs no-print">${["Overview", "🧠 Expert report", "🧩 Profile & parts", "History", "Experts", "Manual", "QR sticker"].map((t, i) => `<button data-tab="${i}" class="${i === 0 ? "on" : ""}">${t}</button>`).join("")}</div>
  <div id="mp-tab"></div>`;
  const kpi = (b, l) => `<div class="kpi"><b>${b}</b><span class="small muted">${l}</span></div>`;
  const tabs = [
    () => `${smartCards(d, a)}<div class="grid g4" style="margin-top:12px">${kpi(d.stats.problems, "problems logged")}${kpi(d.stats.fixed, "fixed")}${kpi(d.stats.hours_lost + " h", "time lost")}${kpi(d.stats.last_problem ? fmtDate(d.stats.last_problem) : "—", "last problem")}</div>
      ${d.sensor ? `<div class="card" style="margin-top:12px;border-left:5px solid ${d.sensor.state === "confirmed" ? "var(--ok)" : "var(--warn)"}"><b>📡 Sensor</b><p class="small" style="margin:4px 0">${esc(d.sensor.text)}</p><div class="tiny muted">${esc(d.sensor.symptom)}</div></div>` : ""}
      <div class="grid g2" style="margin-top:12px">
        <div class="card"><div class="row" style="justify-content:space-between"><h3>🔧 Service due</h3>${d.service_due.length ? `<a class="btn sm" href="/api/i/${S.ind}/machines/${encodeURIComponent(a.id)}/service.ics" download="${esc(a.id)}-service.ics">📅 Add to calendar</a>` : ""}</div>${d.service_due.length ? d.service_due.map((x) => `<div class="li"><span class="badge ${x.status === "overdue" ? "b-failed" : x.status === "soon" ? "b-unreviewed" : "b-verified"}">${x.status === "overdue" ? `${-x.days_left} days overdue` : `in ${x.days_left} days`}</span> <b>${esc(x.what)}</b>
          <div class="tiny muted">Every ${x.every_days} days · ${x.last_done ? `last done ${fmtDate(x.last_done)} (found in repair history)` : x.last_from === "install date" ? "counted from install date" : ""}</div></div>`).join("") : '<p class="small muted">No service intervals yet. Add parts with "replace every N days".</p>'}</div>
        <div class="card"><h3>📦 Spare parts in store</h3>${d.parts.length ? d.parts.map((c) => `<div class="li row" style="justify-content:space-between"><div><b>${esc(c.name)}</b> <span class="tiny muted mono">${esc(c.part_no || "")}</span>
            <div class="tiny muted">${c.status === "out" ? "⛔ none left — order now" : c.status === "low" ? "⚠️ low" : c.status === "ok" ? "ok" : "stock not set"}</div></div>
            <div class="row" style="gap:4px"><button class="btn sm" data-st="${esc(c.name)}" data-d="-1">−</button><b class="mono" style="min-width:22px;text-align:center">${c.stock ?? "?"}</b><button class="btn sm" data-st="${esc(c.name)}" data-d="1">+</button></div></div>`).join("") : '<p class="small muted">No parts listed yet.</p>'}
          <p class="tiny muted">Repair logs that say a part was replaced take one off automatically.</p></div>
        <div class="card"><h3>🧾 Warranty & service</h3>${d.warranty ? `<p><span class="badge ${d.warranty.active ? (d.warranty.days_left <= 45 ? "b-unreviewed" : "b-verified") : "b-failed"}">${d.warranty.active ? `Under warranty — ${d.warranty.days_left} days left` : "Warranty ended"}</span> <span class="small">until ${fmtDate(d.warranty.until)}</span></p>` : '<p class="small muted">No warranty date.</p>'}
          <p class="small">Installed: <b>${a.install_date ? fmtDate(a.install_date) : "—"}</b><br>Service vendor: <b>${esc(a.vendor || "—")}</b></p>
          ${d.twins.length ? `<p class="small">🌐 Same model: ${d.twins.map((t) => `<a href="#/i/${S.ind}/${S.role}/machines/${t}">${esc(t)}</a>`).join(", ")} — their fixes count here too.</p>` : ""}</div>
        <div class="card"><h3>📋 Specs</h3>${d.spec_fields.some((f) => f.value) ? `${specGrid(d.spec_fields.filter((f) => f.value), false, a.id)}<p class="tiny muted">🟢 checked in the maker's document · 🟠 not checked · ✏️ typed by a person. Answers warn when a problem goes past these limits.</p>` : ""}
          ${(a.specs || []).filter((x) => !d.spec_fields.some((f) => f.label === x.label)).length ? `<table class="t">${a.specs.filter((x) => !d.spec_fields.some((f) => f.label === x.label)).map((x) => `<tr><td class="muted small">${esc(x.label)}</td><td class="small">${esc(x.value)}</td></tr>`).join("")}</table>` : ""}
          ${!(a.specs || []).length && !d.spec_fields.some((f) => f.value) ? '<p class="small muted">No specs yet.' + (canEdit ? " Use ✏️ Edit details and give Ustaad the manual or a link." : "") + "</p>" : ""}</div>
        ${d.similar.length ? `<div class="card"><h3>👯 Similar ${esc(L().assets.toLowerCase())}</h3>${d.similar.map((x) => `<div class="li"><a href="#/i/${S.ind}/${S.role}/machines/${encodeURIComponent(x.id)}"><b class="mono">${esc(x.id)}</b></a> ${esc(x.name)} <div class="tiny muted">${esc(x.why)}</div></div>`).join("")}<p class="tiny muted">What fixed those may help here.</p></div>` : ""}
      </div>`,
    () => `<div id="mp-report">${spin} Loading the expert report…</div>`,
    () => `<div id="mp-parts">${spin} Loading the profile…</div>`,
    () => `<div id="mp-patterns">${spin} Pattern detective…</div><div class="card" style="margin-top:12px">${d.history.length ? `<table class="t"><tr><th>Date</th><th>Problem</th><th>What was done</th><th>Result</th><th>By</th></tr>${d.history.map((r) => `<tr><td class="small">${fmtDate(r.date)}</td><td><b>${esc(r.problem)}</b>${r.source === "sensor" ? ' <span class="badge b-site">📡 auto-logged</span>' : ""}</td><td class="small">${esc(r.action)}</td>
        <td><span class="badge ${r.outcome === "fixed" ? "b-verified" : r.outcome === "open" ? "b-unreviewed" : "b-failed"}">${esc(r.outcome_label)}</span>${r.sensor?.confirmed ? ' <span class="badge b-verified">📡 confirmed</span>' : ""}${r.status === "pending" ? ' <span class="badge b-unreviewed">Unreviewed</span>' : ""}</td><td class="small">${esc(r.person)}</td></tr>`).join("")}</table>` : '<p class="muted">No problems logged yet — memory starts here.</p>'}</div>`,
    () => `<div class="grid g3">${d.experts.map((x, i) => `<div class="card"><div class="tiny muted">#${i + 1} on this ${esc(L().asset.toLowerCase())}${d.twins.length ? " and its twins" : ""}</div><h3>${esc(x.name)}</h3><div class="small muted">${esc(x.role)}</div>
        <p><b>${x.fixes}</b> proven fix(es)${x.leaving ? ` · <span class="badge b-high">Leaving ${fmtDate(x.leaving)}</span>` : ""}</p>
        <div class="row"><a class="btn sm" href="#/passport/${S.ind}/${x.person_id}">🏅 Skill passport</a><a class="btn sm ok" target="_blank" rel="noopener" href="https://wa.me/?text=${encodeURIComponent(`${x.name.split(" ")[0]} ji, need your help with ${a.id} (${nm(a)}).`)}">💬 WhatsApp</a></div></div>`).join("") || '<div class="card muted">No proven fixes yet.</div>'}</div>
      ${d.experts.some((x) => x.leaving) ? '<p class="small" style="margin-top:10px">⚠️ An expert here is leaving — run the <b>Exit interview</b> before they go.</p>' : ""}`,
    () => `<div class="row" style="margin-bottom:12px"><button class="btn" id="mq-go">🎓 Quiz me on this ${esc(L().asset.toLowerCase())}</button><span class="tiny muted">5 questions from its own manual and specs</span></div><div id="mp-guides"></div>${d.manual_pages ? `<div class="card" style="margin-bottom:12px;border-left:5px solid var(--accent)"><b>📖 Ask the manual</b> <span class="tiny muted">— ${d.manual_pages} page(s) of ${esc(a.id)}'s manual stored; answers quote the page</span>
        <div class="row" style="flex-wrap:nowrap;margin-top:6px"><input class="field" id="am-q" placeholder="e.g. What air pressure does it need? / Where is relay K1?"><button class="btn accent" id="am-go">Ask</button>
        <label class="btn" title="Photograph a panel, label or part and find it in the manual">📷<input type="file" id="am-photo" accept="image/*" capture="environment" hidden></label></div>
        <div class="tiny muted" style="margin-top:4px">Ask anything · type a tag like <b>K1</b> or <b>SOL-2</b> to find it on the drawings · 📷 photo of a panel or part finds its pages</div><div id="am-out" style="margin-top:8px"></div></div>` : ""}
      <div class="card">${d.manual.length ? `<p class="small muted">From ${esc(a.source_ref || "the maker's manual")}. These are in Ustaad's memory as "📘 Maker's manual", so answers can compare the manual with what your team found.</p>${d.manual.map((m) => `<div class="li"><span class="badge b-manual">${{ fault: "Known fault", service: "Service", spec: "Specs" }[m.kind] || m.kind}</span> <b>${esc(m.title)}</b><div class="small">${esc(m.text)}</div></div>`).join("")}` : `<p class="muted">No manual added yet.${canEdit ? " Use ＋ Add (or ✏️ Edit details) and upload the maker's PDF manual or web page." : ""}</p>`}</div>`,
    () => `<div class="card sticker"><div class="qr"><img src="${qrImg}" alt="QR code for ${esc(a.id)}" width="200" height="200"></div>
        <div><div class="tiny" style="letter-spacing:.12em;text-transform:uppercase;color:var(--accent);font-weight:700">Ustaad · scan me</div><h2 class="mono" style="margin:4px 0">${esc(a.id)}</h2><div>${esc(nm(a))}</div><div class="small muted">${esc(d.site)}</div>
        <p class="small">Problem with this ${esc(L().asset.toLowerCase())}? Scan with your phone camera — Ustaad opens with it already chosen.</p><div class="tiny muted mono">${esc(qrUrl)}</div></div></div>
      <div class="row no-print" style="margin-top:10px"><button class="btn primary" onclick="window.print()">🖨 Print sticker</button><span class="small muted">Like a barcode at a shop — it tells Ustaad which ${esc(L().asset.toLowerCase())} this is.</span></div>`,
  ];
  const show = (i) => { $$(".tabs button", el).forEach((b) => b.classList.toggle("on", +b.dataset.tab === i)); $("#mp-tab").innerHTML = tabs[i]();
    if ($("#am-go")) { const askM = async () => { const q = $("#am-q").value.trim(); if (!q) return; $("#am-out").innerHTML = `${spin} Looking through the manual…`;
      try { const r = await api(`/api/i/${S.ind}/machines/${encodeURIComponent(a.id)}/ask-manual`, { json: { question: q } });
        $("#am-out").innerHTML = `<p class="small" style="margin:0">${esc(r.answer)}</p>${(r.steps || []).length ? `<ol class="small">${r.steps.map((x) => `<li>${esc(x)}</li>`).join("")}</ol>` : ""}${(r.drawing || []).length ? `<div class="card" style="margin-top:8px;background:#f8fafc"><b class="small">🔌 Found on the drawings</b>${r.drawing.map((h) => `<div class="li small"><b class="mono">${esc(h.tag)}</b> ${h.drawing ? '<span class="badge b-src">drawing</span>' : ""} ${pgLink(a.id, h.page, h.src, h.tag, h.label)} <span class="muted">…${esc(h.context)}…</span></div>`).join("")}</div>` : ""}
        <div class="tiny muted">Pages used: ${(r.refs || []).map((x) => pgLink(a.id, x.page, x.src, "", x.label)).join(" · ") || "—"} · by ${esc(r.written_by)}</div>`; }
      catch (err) { $("#am-out").innerHTML = `<span class="small" style="color:var(--bad)">${esc(err.message)}</span>`; } };
      $("#am-go").onclick = askM; $("#am-q").onkeydown = (ev) => { if (ev.key === "Enter") askM(); }; }
    if ($("#am-photo")) $("#am-photo").onchange = async (ev) => { const f = ev.target.files[0]; if (!f) return; $("#am-out").innerHTML = `${spin} Reading the photo and searching the manual…`;
      const fd = new FormData(); fd.append("image", f);
      try { const r = await api(`/api/i/${S.ind}/machines/${encodeURIComponent(a.id)}/photo-pages`, { method: "POST", body: fd });
        $("#am-out").innerHTML = `<div class="tiny muted">📷 Read by ${esc(r.read_by)}: “${esc(r.read.slice(0, 160))}”</div>${r.pages.length ? r.pages.map((x) => `<div class="li small">${pgLink(a.id, x.page, x.src, "", x.label)} <span class="muted">${esc(x.snippet)}…</span></div>`).join("") : '<p class="small">No matching page found.</p>'}`; }
      catch (err) { $("#am-out").innerHTML = `<span class="small" style="color:var(--bad)">${esc(err.message)}</span>`; } };
    if ($("#mp-report")) reportTab($("#mp-report"), a, canEdit);
    if ($("#mq-go")) $("#mq-go").onclick = () => { S.prefill = { quiz_asset: a.id }; go(`#/i/${S.ind}/${S.role}/quiz`); };
    if ($("#mp-guides")) loadGuides($("#mp-guides"), a.id);
    if ($("#mp-patterns")) patternsCard($("#mp-patterns"), a);
    if ($("#up-stop")) $("#up-stop").onclick = () => stopForm({ ...a, _stopReasons: d.stop_reasons }, () => machineProfile(el, aid));
    if ($("#up-hours")) $("#up-hours").onclick = async () => { const v = prompt("Hour meter reading now (hours)?"); if (!v) return;
      try { await api(`/api/i/${S.ind}/machines/${encodeURIComponent(a.id)}/hours`, { json: { hours: +v } }); machineProfile(el, aid); } catch (err) { toast(esc(err.message), "alert"); } };
    if ($("#mp-parts")) partsTab($("#mp-parts"), a, d);
    $$("[data-st]", el).forEach((b) => (b.onclick = async () => { const c = d.parts.find((x) => x.name === b.dataset.st); const v = Math.max(0, (+c.stock || 0) + +b.dataset.d);
      try { await api(`/api/i/${S.ind}/machines/${encodeURIComponent(a.id)}/stock`, { json: { part: c.name, stock: v } }); machineProfile(el, aid); } catch (err) { toast(esc(err.message), "alert"); } })); };
  $$(".tabs button", el).forEach((b) => (b.onclick = () => show(+b.dataset.tab))); show(S.mpTab || 0); S.mpTab = 0;
  $("#mp-ask").onclick = () => { S.prefill = { asset_id: a.id }; go(`#/i/${S.ind}/${S.role}/ask`); };
  $("#mp-log").onclick = () => go(`#/i/${S.ind}/${S.role}/log`);
  if ($("#mp-edit")) $("#mp-edit").onclick = () => machineForm($("#mp-form"), a);
  guideHook("profile");
}
// ---------- manual page viewer (opens beside the answer; full screen on phones) ----------
function pgLink(aid, n, src, quote, label) {
  return `<a href="#" class="pg" data-aid="${esc(aid)}" data-n="${esc(n)}" data-src="${esc(src || "")}" data-q="${esc(quote || "")}">📄 ${esc(label || "p." + n)}</a>`;
}
document.addEventListener("click", (e) => { const t = e.target.closest?.(".pg"); if (!t) return; e.preventDefault(); openPage(t.dataset.aid, t.dataset.n, t.dataset.src, t.dataset.q); });
async function openPage(aid, n, src, quote) {
  $("#pg-drawer")?.remove();
  const dr = document.createElement("div"); dr.id = "pg-drawer"; dr.className = "drawer";
  dr.innerHTML = `<div class="row" style="justify-content:space-between"><b>📄 Page ${esc(n)}</b><button class="btn sm" id="pg-x">✕ Close</button></div><div id="pg-body">${spin}</div>`;
  document.body.appendChild(dr); $("#pg-x").onclick = () => dr.remove();
  try {
    const p = await api(`/api/i/${S.ind}/machines/${encodeURIComponent(aid)}/page?n=${encodeURIComponent(n)}&src=${encodeURIComponent(src || "")}`);
    const text = p.text.replace(/[ \t]+/g, " "); let html = esc(text);
    const q = (quote || "").replace(/\s+/g, " ").trim();
    if (q) { const low = text.toLowerCase(); let i = low.indexOf(q.toLowerCase()), len = q.length;
      if (i < 0) { const w = q.split(" ").slice(0, 5).join(" ").toLowerCase(); i = w.length > 4 ? low.indexOf(w) : -1; len = w.length; }
      if (i >= 0) html = esc(text.slice(0, i)) + "<mark id='pg-hit'>" + esc(text.slice(i, i + len)) + "</mark>" + esc(text.slice(i + len)); }
    $("#pg-body").innerHTML = `<div class="tiny muted">${esc(p.source)} · page ${p.page} · ${p.via === "sarvam-ocr" ? "read by Sarvam Vision" : p.via === "vision" ? "read by the vision AI" : "text of the page"}</div><pre class="pg-text">${html}</pre>`;
    $("#pg-hit")?.scrollIntoView({ block: "center" });
  } catch (err) { $("#pg-body").innerHTML = `<p class="small" style="color:var(--bad)">${esc(err.message)}</p>`; }
}
// ---------- expert report ----------
const basisTag = (aid, x) => x.basis === "manual" ? `<span class="badge b-verified" title="The quote is really on this page">📘 Manual</span> ${x.page ? pgLink(aid, x.page, "", x.quote || "", "p." + x.page) : ""}`
  : x.basis === "unchecked" ? `<span class="badge b-unreviewed" title="Said to be from the manual, but the quote wasn't found">📘? check</span> ${x.page ? pgLink(aid, x.page, "", "", "p." + x.page) : ""}`
  : `<span class="badge b-site" title="A conclusion drawn by the expert read">🧠 Expert conclusion</span>`;
async function reportTab(box, a, canEdit) {
  let v;
  try { v = await api(`/api/i/${S.ind}/machines/${encodeURIComponent(a.id)}/report`); } catch (err) { box.innerHTML = `<div class="card">${esc(err.message)}</div>`; return; }
  const pr = v.progress, r = v.report, m = v.meta;
  const rebuild = canEdit ? `<button class="btn sm" id="rp-go">${r ? "🔄 Read again" : "▶ Build the report"}</button>` : "";
  if (pr && pr.state === "running") {
    box.innerHTML = `<div class="card"><b>${spin} The expert read is running</b><p class="small">${esc(v.expert)} is reading ${v.manual_pages} manual page(s)${pr.total ? ` — section ${pr.done} of ${pr.total}` : ""}. Groq and Sarvam read different sections at the same time. A 200-page manual takes 2–4 minutes.</p></div>`;
    setTimeout(() => { if (document.body.contains(box)) reportTab(box, a, canEdit); }, 3500); return;
  }
  if (!r) {
    box.innerHTML = `<div class="card"><h3>🧠 Expert report</h3><p class="small">${v.manual_pages ? "The manual is stored but the report isn't built yet." : "Add the maker's manual or product link (✏️ Edit details) and the expert read starts by itself."}</p>${pr && pr.state === "failed" ? `<p class="small" style="color:var(--bad)">Last try failed: ${esc(pr.error || "")}</p>` : ""}${rebuild}</div>`;
    if ($("#rp-go")) $("#rp-go").onclick = async () => { await api(`/api/i/${S.ind}/machines/${encodeURIComponent(a.id)}/report`, { json: {} }); reportTab(box, a, canEdit); };
    return;
  }
  const li = (x, main, sub) => `<div class="li"><div><b>${esc(main)}</b> ${basisTag(a.id, x)}</div>${sub ? `<div class="small muted">${sub}</div>` : ""}</div>`;
  const mt = r.maintenance || {};
  box.innerHTML = `<div class="card" style="border-top:4px solid var(--accent)"><div class="row" style="justify-content:space-between"><h3>🧠 Expert report</h3>${rebuild}</div>
      <p style="margin:6px 0">${esc(r.summary || "")}</p>${r.what_it_is ? `<p class="small muted">${esc(r.what_it_is)}</p>` : ""}
      <div class="tiny muted">Read as ${esc(v.expert)} · ${m ? `${m.pages_read} page(s) in ${m.sections} section(s) by ${esc(m.by)} · ${fmtDate(m.built)}` : ""} · 📘 = the quote is on that page (checked by code) · 🧠 = expert conclusion</div></div>
    <div class="grid g2" style="margin-top:12px">
      <div class="card"><h3>✅ Good for</h3>${(r.good_for || []).map((x) => `<div class="li small">${esc(x)}</div>`).join("") || '<p class="small muted">—</p>'}</div>
      <div class="card"><h3>⛔ Not good for</h3>${(r.not_good_for || []).map((x) => `<div class="li small">${esc(x)}</div>`).join("") || '<p class="small muted">—</p>'}</div></div>
    <div class="card" style="margin-top:12px"><h3>📏 Working window</h3>${(r.operating_window || []).length ? `<table class="t">${r.operating_window.map((x) => `<tr><td class="small">${esc(x.what)}</td><td class="small"><b>${esc(x.range)}</b></td><td>${basisTag(a.id, x)}</td></tr>`).join("")}</table>` : '<p class="small muted">—</p>'}</div>
    <div class="card" style="margin-top:12px"><h3>💥 What will probably break first</h3>${(r.likely_failures || []).map((x, i) => li(x, `${i + 1}. ${x.part}`, `${esc(x.why || "")}${x.signs ? `<br>Signs: ${esc(x.signs)}` : ""}${(x.alarm_codes || []).filter(Boolean).length ? `<br>Alarms: ${x.alarm_codes.map((c) => `<span class="badge b-src mono">${esc(c)}</span>`).join(" ")}` : ""}${x.because ? `<br><i>Because: ${esc(x.because)}</i>` : ""}`)).join("") || '<p class="small muted">—</p>'}</div>
    <div class="card" style="margin-top:12px"><h3>🗓️ Maintenance plan</h3><div class="grid g4">${["daily", "weekly", "monthly", "yearly"].map((k) => `<div><b class="small">${k[0].toUpperCase() + k.slice(1)}</b>${(mt[k] || []).map((x) => `<div class="li small">${esc(x.task || "")} ${x.basis === "manual" && x.page ? pgLink(a.id, x.page, "", x.quote || "", "p." + x.page) : x.basis === "expert" ? "🧠" : ""}</div>`).join("") || '<div class="tiny muted">—</div>'}</div>`).join("")}</div></div>
    <div class="grid g2" style="margin-top:12px">
      <div class="card"><h3>📦 Critical spares to stock</h3>${(r.critical_spares || []).map((x) => `<div class="li small"><b>${esc(x.name)}</b> <span class="mono tiny">${esc(x.part_no || "")}</span><div class="muted">${esc(x.why || "")}</div></div>`).join("") || '<p class="small muted">—</p>'}</div>
      <div class="card"><h3>⚠️ Safety</h3>${(r.safety || []).map((x) => li(x, x.text, "")).join("") || '<p class="small muted">—</p>'}</div></div>
    <div class="card" style="margin-top:12px;background:#fff7e6"><h3>❓ What the manual doesn't tell you</h3>${(r.gaps || []).map((x) => `<div class="li small">${esc(x)}</div>`).join("") || '<p class="small muted">—</p>'}
      <button class="btn sm" id="rp-vendor" style="margin-top:6px">📨 Ask the vendor</button></div>`;
  if ($("#rp-go")) $("#rp-go").onclick = async () => { await api(`/api/i/${S.ind}/machines/${encodeURIComponent(a.id)}/report`, { json: {} }); reportTab(box, a, canEdit); };
  $("#rp-vendor").onclick = () => vendorMsg(a);
}
async function vendorMsg(a) {
  const r = await api(`/api/i/${S.ind}/machines/${encodeURIComponent(a.id)}/vendor-message`);
  const phone = (a.vendor_phone || "").replace(/[^0-9]/g, "");
  $("#pg-drawer")?.remove(); const dr = document.createElement("div"); dr.id = "pg-drawer"; dr.className = "drawer";
  dr.innerHTML = `<div class="row" style="justify-content:space-between"><b>📨 Ask the vendor</b><button class="btn sm" id="pg-x">✕</button></div>
    <p class="small muted">Everything the profile is missing, in one message.</p><textarea class="field" style="min-height:220px" id="vm-t">${esc(r.text)}</textarea>
    <div class="row" style="margin-top:8px"><a class="btn accent" target="_blank" rel="noopener" href="https://wa.me/${phone}?text=${encodeURIComponent(r.text)}">WhatsApp</a>
    <a class="btn" href="mailto:?subject=${encodeURIComponent("Details for " + (a.name || a.id))}&body=${encodeURIComponent(r.text)}">Email</a><button class="btn" id="vm-c">Copy</button></div>`;
  document.body.appendChild(dr); $("#pg-x").onclick = () => dr.remove();
  $("#vm-c").onclick = () => { navigator.clipboard?.writeText($("#vm-t").value); toast("Copied"); };
}
// ---------- universal profile + part tree ----------
async function partsTab(box, a, d) {
  let v; try { v = await api(`/api/i/${S.ind}/machines/${encodeURIComponent(a.id)}/report`); } catch (err) { box.innerHTML = `<div class="card">${esc(err.message)}</div>`; return; }
  const c = v.completeness, crit = { A: ["b-failed", "A · stops production"], B: ["b-unreviewed", "B · important"], C: ["b-src", "C · consumable"] };
  const layer = (title, obj) => `<div class="card"><h3>${title}</h3><table class="t">${Object.values(obj || {}).map((x) => `<tr><td class="muted small">${esc(x.label)}</td>
      <td class="small">${x.value ? `<b>${esc(x.value)}</b> ${x.checked ? "🟢" : "🟠"} ${x.page ? pgLink(a.id, x.page, "", x.quote || "", "p." + x.page) : x.source && x.source !== "entered" ? `<span class="tiny muted">${esc(x.source)}</span>` : ""}` : '<span class="muted">— missing</span>'}</td></tr>`).join("")}</table></div>`;
  const links = v.part_tree.flatMap((g) => g.parts).filter((p) => (p.alarm_codes || []).length);
  box.innerHTML = `<div class="card" style="border-top:4px solid var(--accent)"><div class="row" style="justify-content:space-between;align-items:center"><div><h3 style="margin:0">🪪 Universal profile</h3>
      <div class="tiny muted">One standard for every machine, in 5 layers (based on ISO 14224, the international standard for maintenance data)</div></div>
      <div style="min-width:200px"><b>${c.pct}% complete</b><div class="lvl-bar"><i style="width:${c.pct}%"></i></div><div class="tiny muted">${c.filled}/${c.fields} details · ${c.parts_with_no}/${c.parts} parts have a part number</div></div></div>
      ${c.missing.length || c.parts_missing_no.length ? `<p class="small" style="margin:8px 0 0">Missing: ${esc(c.missing.slice(0, 8).join(", "))}${c.missing.length > 8 ? "…" : ""} <button class="btn sm" id="pp-vendor">📨 Ask the vendor</button></p>` : ""}</div>
    <div class="grid g2" style="margin-top:12px">${layer("1 · Identity", v.universal.identity)}${layer("2 · Core ratings", v.universal.core)}</div>
    <div class="card" style="margin-top:12px"><h3>3 · ${esc(a.template ? "Type-specific specs" : "Specs")}</h3>${d.spec_fields.some((f) => f.value) ? specGrid(d.spec_fields.filter((f) => f.value), false, a.id) : (a.specs || []).length ? `<table class="t">${a.specs.map((x) => `<tr><td class="muted small">${esc(x.label)}</td><td class="small">${esc(x.value)}</td></tr>`).join("")}</table>` : '<p class="small muted">No specs yet.</p>'}</div>
    <div class="card" style="margin-top:12px"><h3>4 · Part tree</h3><p class="tiny muted">Tap a part for everything about it: details, manual page, service, stock, alarms and the team's real fixes.</p>
      ${v.part_tree.length ? v.part_tree.map((g) => `<details open><summary><b>${esc(g.assembly)}</b> <span class="tiny muted">(${g.parts.length})</span></summary><div class="row" style="gap:6px;margin:6px 0 10px">${g.parts.map((p) => `<button class="chip-part" data-pid="${esc(p.id)}"><span class="badge ${crit[p.criticality]?.[0] || "b-src"}">${esc(p.criticality || "B")}</span> ${esc(p.name)}${p.part_no ? ` <span class="mono tiny">${esc(p.part_no)}</span>` : ""}${p.stock != null ? ` <span class="tiny">· ${p.stock} in store</span>` : ""}</button>`).join("")}</div></details>`).join("") : '<p class="small muted">No parts yet — the expert read builds this from the manual\'s parts lists and drawings.</p>'}
      <div class="tiny muted">A = stops production when it fails · B = important · C = consumable</div></div>
    <div class="card" style="margin-top:12px"><h3>5 · Links</h3>${links.length ? links.map((p) => `<div class="li small">${p.alarm_codes.map((x) => `<span class="badge b-src mono">${esc(x)}</span>`).join(" ")} → <b>${esc(p.name)}</b></div>`).join("") : '<p class="small muted">Alarms linked to parts appear here after the expert read.</p>'}</div>`;
  $$(".chip-part", box).forEach((b) => (b.onclick = () => partPanel(a, b.dataset.pid)));
  if ($("#pp-vendor")) $("#pp-vendor").onclick = () => vendorMsg(a);
}
async function partPanel(a, pid) {
  $("#pg-drawer")?.remove(); const dr = document.createElement("div"); dr.id = "pg-drawer"; dr.className = "drawer"; dr.innerHTML = spin; document.body.appendChild(dr);
  try {
    const r = await api(`/api/i/${S.ind}/machines/${encodeURIComponent(a.id)}/part/${encodeURIComponent(pid)}`); const p = r.part;
    const row = (k, v) => v ? `<tr><td class="muted small">${k}</td><td class="small">${v}</td></tr>` : "";
    dr.innerHTML = `<div class="row" style="justify-content:space-between"><b>🧩 ${esc(p.name)}</b><button class="btn sm" id="pg-x">✕</button></div>
      <div class="tiny muted">${esc(a.id)} · ${esc(p.assembly || "")}</div>
      <table class="t" style="margin-top:8px">${row("Part number", p.part_no ? `<b class="mono">${esc(p.part_no)}</b>` : "")}${row("Quantity", esc(p.qty || ""))}${row("Spec", esc(p.spec || ""))}
        ${row("Replace / service", esc(p.interval || (p.every_days ? `every ${p.every_days} days` : "")))}${row("Signs it's failing", esc(p.failure_signs || ""))}
        ${row("Alarm codes", (p.alarm_codes || []).map((c) => `<span class="badge b-src mono">${esc(c)}</span>`).join(" "))}
        ${row("How critical", { A: "A · stops production", B: "B · important", C: "C · consumable" }[p.criticality] || "")}
        ${row("In store", p.stock != null ? `${p.stock}` : "")}${row("Service due", r.service_due ? (r.service_due.status === "overdue" ? `<b style="color:var(--bad)">${-r.service_due.days_left} days overdue</b>` : `in ${r.service_due.days_left} days`) : "")}
        ${row("Manual", p.page ? pgLink(a.id, p.page, "", p.quote || "", "page " + p.page) + (p.checked ? " 🟢" : "") : "")}</table>
      <h3 style="margin-top:12px">🛠️ The team's real fixes on this part</h3>${r.fixes.length ? r.fixes.map((f) => `<div class="li small"><b>${esc(f.problem)}</b> <span class="tiny muted">${fmtDate(f.date)} · ${esc(f.person)}</span><div>${esc(f.action)} — <b>${esc(OUTCOME[f.outcome] || f.outcome)}</b></div></div>`).join("") : '<p class="small muted">No fixes on this part logged yet.</p>'}`;
    $("#pg-x").onclick = () => dr.remove();
  } catch (err) { dr.innerHTML = `<p class="small" style="color:var(--bad)">${esc(err.message)}</p>`; }
}
// ---------- smart diagnosis ----------
// 🌐 plants learning from each other (names hidden)
function netCard(o) {
  if (!o) return "";
  const col = (r) => (r >= 0.7 ? "var(--ok)" : r >= 0.4 ? "var(--warn)" : "var(--bad)");
  return `<div class="card net" style="margin-top:12px"><h3>🌐 In other ${esc(o.word)}</h3>
    <p class="small muted" style="margin:2px 0 8px">${o.cases} cases of “${esc(o.problem)}” from ${o.plants} other ${esc(o.word)} with ${esc(o.match)}.</p>
    ${o.fixes.map((f) => `<div class="net-row"><div class="small"><b data-tr>${esc(f.fix)}</b></div>
      <div class="prow" style="margin:3px 0 0"><div class="pbar"><i style="width:${Math.round(f.rate * 100)}%;background:${col(f.rate)}"></i></div>
      <span class="tiny"><b>worked ${f.worked} of ${f.tried}</b>${f.avg_minutes ? ` · ~${f.avg_minutes} min` : ""}</span></div></div>`).join("")}
    <div class="tiny muted" style="margin-top:8px">🔒 Names, companies and places are never shared.${o.sample ? " <b>Sample data</b> in this demo." : ""}</div>
    <label class="tiny eng-only" style="display:flex;gap:6px;align-items:center;margin-top:6px"><input type="checkbox" id="net-share" disabled> Our team shares its fixes too (names removed)</label></div>`;
}
async function bindNetShare(root) {
  const cb = $("#net-share", root); if (!cb) return;
  try { const st = await api(`/api/i/${S.ind}/network/settings`); cb.checked = st.share; cb.disabled = false;
    cb.onchange = async () => { const r = await api(`/api/i/${S.ind}/network/settings`, { json: { share: cb.checked } }); toast(r.share ? "Sharing on — names are always removed." : "Sharing off."); }; } catch { /* leave it disabled */ }
}
function diagCard(g) {
  const bar = (p) => `<div class="pbar"><i style="width:${Math.round(p * 100)}%"></i></div>`;
  return `<div class="card diag"><div class="row" style="justify-content:space-between"><b>🎯 What it usually is — from ${g.cases} past case${g.cases === 1 ? "" : "s"} like this</b><span class="tiny muted" title="${esc(g.how)}">how is this worked out? ⓘ</span></div>
    ${g.causes.map((c) => `<div class="prow"><span class="small" style="min-width:150px"><b data-tr>${esc(c.label)}</b>${c.faded ? ' <span class="badge b-failed">⏳ failed since</span>' : ""}</span>${bar(c.p)}<b>${Math.round(c.p * 100)}%</b>
      <span class="tiny muted">${c.fixed ? `${c.fixed}× fixed it` : ""}${c.failed ? ` · ${c.failed}× didn't` : ""}${c.people.length ? ` · ${esc(c.people.join(", "))}` : ""}</span></div>`).join("")}
    <div class="prow"><span class="small muted" style="min-width:150px">Something else</span>${bar(g.other)}<span class="tiny muted">${Math.round(g.other * 100)}%</span></div>
    ${g.check_order.length ? `<div class="first" style="margin-top:8px">🧠 <b>Smartest order to check</b> (best chance per minute first): ${g.check_order.map((x, i) => `${i + 1}. <span data-tr>${esc(x.label)}</span> <span class="tiny">(${Math.round(x.p * 100)}%, ~${x.minutes} min${x.time_known ? "" : " est."})</span>`).join(" → ")}
      <div class="tiny muted">Average time to find it this way: ~${g.expected_minutes} min${g.expected_minutes_worst_order > g.expected_minutes ? ` (vs ~${g.expected_minutes_worst_order} min in the worst order)` : ""} · confidence: ${g.confidence}</div></div>` : ""}
    ${g.dont_start_with.length ? `<div class="small" style="margin-top:6px">⛔ Don't start with: ${g.dont_start_with.map((x) => `${esc(x.label)} (didn't work ${x.failed}×)`).join(", ")}</div>` : ""}</div>`;
}
function costCard(c, wide) {
  return `<div class="card" style="margin-top:14px;border-left:5px solid var(--bad)"><h3>💸 Cost of not asking Ustaad</h3>
    <p class="small">${c.count} repair${c.count === 1 ? "" : "s"} where the team's working fix was <b>already in memory</b>, but something else was tried first: <b>${c.hours} h</b> and <b>${rupees(c.money)}</b> lost.</p>
    ${c.incidents.slice(0, wide ? 8 : 4).map((x) => `<div class="li small"><b>${fmtDate(x.date)} · ${esc(x.asset_id)} · ${esc(x.problem)}</b><div>Tried: ${esc(x.tried)} — <b>${x.hours} h, ${rupees(x.money)}</b></div><div class="muted">Already known: ${esc(x.known_fix)} (${esc(x.known_by)}, ${esc(x.known_from)})</div></div>`).join("")}</div>`;
}
function smartCards(d, a) {
  const u = d.uptime || {}, pl = d.part_life || [];
  return `<div class="grid g2">
    <div class="card"><div class="row" style="justify-content:space-between"><h3>⏱️ Uptime (last ${u.days} days)</h3><button class="btn sm" id="up-stop">⏹ Log a stop</button></div>
      <div class="row" style="gap:14px;align-items:baseline"><b style="font-size:26px">${u.uptime_pct}%</b><span class="small muted">${u.lost_hours} h lost of ${u.planned_hours} h planned${u.money ? ` · ${rupees(u.money)}` : ""}</span></div>
      ${(u.reasons || []).map((r) => `<div class="prow"><span class="small" style="min-width:140px">${esc(r.reason)}</span><div class="pbar"><i style="width:${Math.min(100, Math.round(100 * r.hours / Math.max(u.lost_hours, 0.1)))}%"></i></div><span class="small">${r.hours} h</span></div>`).join("") || '<p class="small muted">No stops logged.</p>'}</div>
    <div class="card"><div class="row" style="justify-content:space-between"><h3>⚙️ Part life by running hours</h3><button class="btn sm" id="up-hours">🕒 Hour meter</button></div>
      <div class="tiny muted">${d.hour_meter ? `Hour meter: ${Math.round(d.hour_meter.hours).toLocaleString("en-IN")} h on ${fmtDate(d.hour_meter.date)}` : "No hour-meter reading yet — estimated from the calendar"}${Object.keys(d.maker_limits || {}).length ? ` · Sensor limits from the maker: ${Object.values(d.maker_limits).map(esc).join("; ")}` : ""}</div>
      ${pl.length ? pl.map((x) => `<div class="prow"><span class="small" style="min-width:140px">${esc(x.part)}</span><div class="pbar ${x.status}"><i style="width:${Math.min(100, x.pct)}%"></i></div><span class="small">${x.used_hours.toLocaleString("en-IN")} / ${x.life_hours.toLocaleString("en-IN")} h</span></div>`).join("") + `<div class="tiny muted">${esc(pl[0].source)}</div>` : '<p class="small muted">Parts with a life in hours (from the expert read of the manual) show here.</p>'}</div></div>
    ${d.cost && d.cost.count ? costCard(d.cost, false) : ""}`;
}
async function stopForm(a, done) {
  $("#pg-drawer")?.remove(); const dr = document.createElement("div"); dr.id = "pg-drawer"; dr.className = "drawer";
  const reasons = Object.entries(a._stopReasons || { breakdown: "Breakdown", waiting_part: "Waiting for a part", no_operator: "No operator", setup: "Setup / changeover", planned: "Planned maintenance", power: "Power cut", quality: "Quality check", other: "Other" });
  dr.innerHTML = `<div class="row" style="justify-content:space-between"><b>⏹ Why did ${esc(a.id)} stop?</b><button class="btn sm" id="pg-x">✕</button></div>
    <div class="row" style="gap:6px;margin:10px 0">${reasons.map(([k, v], i) => `<button class="chip-part ${i === 0 ? "on" : ""}" data-r="${k}">${esc(v)}</button>`).join("")}</div>
    <label class="f">How long (minutes)</label><input class="field" id="st-min" type="number" value="30" min="1">
    <label class="f">What did you do? <span class="muted small">(for a breakdown this becomes a memory)</span></label><textarea class="field" id="st-note" placeholder="e.g. coupling spider worn, replaced it, vibration gone"></textarea>
    <button class="btn accent" id="st-go" style="margin-top:10px">Save</button>`;
  document.body.appendChild(dr); $("#pg-x").onclick = () => dr.remove();
  let reason = reasons[0][0];
  $$("[data-r]", dr).forEach((b) => (b.onclick = () => { reason = b.dataset.r; $$("[data-r]", dr).forEach((x) => x.classList.toggle("on", x === b)); }));
  $("#st-go").onclick = async () => { try { const r = await api(`/api/i/${S.ind}/machines/${encodeURIComponent(a.id)}/stop`, { json: { reason, minutes: +$("#st-min").value, note: $("#st-note").value, person_id: S.person } });
    dr.remove(); toast(`Saved. Uptime now ${r.uptime.uptime_pct}%` + (r.memory ? " · the fix was saved to memory" : "")); done(); } catch (err) { toast(esc(err.message), "alert"); } };
}
async function patternsCard(box, a) {
  let p; try { p = await api(`/api/i/${S.ind}/machines/${encodeURIComponent(a.id)}/patterns`); } catch { box.innerHTML = ""; return; }
  const ev = p.events; if (!ev.length) { box.innerHTML = ""; return; }
  const t0 = new Date(ev[0].date).getTime(), t1 = Math.max(new Date(ev[ev.length - 1].date).getTime(), t0 + 864e5), W = 900;
  const x = (dt) => 20 + (W - 40) * (new Date(dt).getTime() - t0) / (t1 - t0);
  const col = (e) => e.kind === "stop" ? "#64748b" : e.outcome === "fixed" ? "#16a34a" : e.outcome === "failed_again" ? "#dc2626" : e.outcome === "temporary" ? "#f59e0b" : e.kind === "sensor" ? "#7c3aed" : "#0ea5e9";
  const rows = {}; let lane = 0; const laneOf = (k) => (rows[k] ??= lane++);
  ev.forEach((e) => laneOf(e.kind === "stop" ? "Stops" : (e.code || e.title)));
  const H = 30 + 22 * Math.max(1, lane);
  box.innerHTML = `<div class="card"><h3>🔍 Pattern detective</h3>
    <div style="overflow-x:auto"><svg viewBox="0 0 ${W} ${H}" style="width:100%;min-width:560px;height:${H}px">
      ${Object.entries(rows).map(([k, i]) => `<text x="0" y="${22 + 22 * i}" font-size="10" fill="#64748b"></text><line x1="20" x2="${W - 20}" y1="${18 + 22 * i}" y2="${18 + 22 * i}" stroke="#eef0f3"/>`).join("")}
      ${ev.map((e) => `<circle cx="${x(e.date)}" cy="${18 + 22 * rows[e.kind === "stop" ? "Stops" : (e.code || e.title)]}" r="6" fill="${col(e)}"><title>${esc(e.date)} · ${esc(e.title)}${e.code ? " (" + esc(e.code) + ")" : ""} · ${esc(e.outcome || e.kind)} · ${esc(e.action || "")}</title></circle>`).join("")}
      <text x="20" y="${H - 2}" font-size="10" fill="#94a3b8">${esc(ev[0].date)}</text><text x="${W - 20}" y="${H - 2}" font-size="10" fill="#94a3b8" text-anchor="end">${esc(ev[ev.length - 1].date)}</text></svg></div>
    <div class="tiny muted">Each row is one problem; 🟢 worked · 🔴 didn't work · 🟠 temporary · 🟣 sensor · ⚪ stop. Hover a dot for details.</div>
    ${p.findings.length ? `<h3 style="margin-top:10px">What the pattern says</h3>${p.findings.map((f) => `<div class="li small"><b>${esc(f.text)}</b><div class="muted">→ ${esc(f.suggest)}</div></div>`).join("")}` : '<p class="small muted">Not enough history for patterns yet.</p>'}</div>`;
}
async function benchView(el) {
  const d = await api("/api/benchmark"); const o = d.overall;
  const pct = (r) => (r && r.total ? `<span class="badge ${r.pct >= 90 ? "b-verified" : r.pct >= 60 ? "b-unreviewed" : "b-failed"}">${r.pct}% · ${r.passed}/${r.total}</span>` : '<span class="badge b-src">not run yet</span>');
  el.innerHTML = `<div class="crumbs"><a href="#/i/${S.ind}/${S.role}/machines">← My ${esc(L().assets.toLowerCase())}</a></div>
  <div class="panel-head"><div><h2>📏 How accurate is the reader?</h2><p class="muted small">Real maker documents with answers we checked by hand. Ustaad reads each one like a new machine,
    then every value is compared after unit conversion (64 cfm = 1812 l/min). Nothing is hidden: wrong answers and blocked sites show here too.</p></div></div>
  <div class="grid g3"><div class="kpi"><b>${o.pct == null ? "—" : o.pct + "%"}</b><span class="small muted">of checked values right</span></div>
    <div class="kpi"><b>${o.passed}/${o.total}</b><span class="small muted">values right, across ${o.cases_run} document(s)</span></div>
    <div class="kpi"><b>${d.ai ? "On" : "Off"}</b><span class="small muted">AI (${d.ai ? "Groq identifies the model and reads text" : "tables and text lines only"})</span></div></div>
  <div class="row" style="margin:12px 0"><button class="btn accent" id="bn-run" ${d.running ? "disabled" : ""}>${d.running ? `${spin} Running ${esc(d.current || "")}…` : "▶ Run the web tests"}</button>
    <label class="btn">📄 Score an uploaded manual<input type="file" id="bn-file" accept="application/pdf" hidden></label><span class="small muted" id="bn-msg">Web tests take ~25 s each (spaced out for the free AI limit).</span></div>
  ${d.cases.map((c) => { const r = c.last; return `<div class="card" style="margin-bottom:10px"><div class="row" style="justify-content:space-between"><div><b>${esc(c.title)}</b>
      <div class="tiny muted">${c.kind === "url" ? `🌐 <a href="${esc(c.source)}" target="_blank" rel="noopener">${esc(c.source.slice(0, 80))}…</a>` : "📄 runs when this exact file is uploaded (matched by fingerprint)"}${r ? ` · ran ${fmtDate(r.when)} in ${r.seconds}s · AI ${r.ai ? "on" : "off"}` : ""}</div></div>${pct(r)}</div>
    ${r && r.error ? `<p class="small" style="color:var(--bad)">⚠️ ${esc(r.error)}</p>` : ""}
    ${r && r.checks.length ? `<table class="t bench"><tr><th></th><th>What</th><th>Right answer</th><th>Ustaad read</th></tr>${r.checks.map((x) => `<tr><td>${x.ok ? "✅" : "❌"}</td><td>${esc(x.what)}<div class="tiny muted">${esc(x.why)}</div></td><td class="mono">${esc(x.want)}</td><td>${esc(x.got)}</td></tr>`).join("")}</table>` : ""}</div>`; }).join("")}`;
  $("#bn-run").onclick = async () => { try { await api("/api/benchmark/run", { json: {} }); toast("Started — this page refreshes as results come in"); poll(); } catch (err) { toast(esc(err.message), "alert"); } };
  $("#bn-file").onchange = async (ev) => { const f = ev.target.files[0]; if (!f) return; const fd = new FormData(); fd.append("file", f); $("#bn-msg").innerHTML = `${spin} Reading ${esc(f.name)}…`;
    try { const r = await api("/api/benchmark/file", { method: "POST", body: fd }); if (!r.matched) { $("#bn-msg").textContent = r.message; return; } benchView(el); } catch (err) { $("#bn-msg").innerHTML = `<span style="color:var(--bad)">${esc(err.message)}</span>`; } };
  const poll = () => { const t = setInterval(async () => { if (!document.body.contains(el) || !location.hash.endsWith("/accuracy")) return clearInterval(t);
    const n = await api("/api/benchmark").catch(() => null); if (n && !n.running) { clearInterval(t); benchView(el); } else if (n) $("#bn-run").innerHTML = `${spin} Running ${esc(n.current || "")}…`; }, 5000); S.charts.push({ destroy: () => clearInterval(t) }); };
  if (d.running) poll();
}
function openFromQR(ind, aid) {  // the QR sticker: open Ask as a worker with this item already chosen
  return loadPack(ind).then((p) => { const r = p.roles.find((x) => !x.can_approve && x.tools.includes("ask")) || p.roles[0];
    S.prefill = { asset_id: aid }; toast(`📷 Scanned ${esc(aid)} — what's the problem?`); location.replace(`#/i/${ind}/${r.id}/ask`); });
}

// ---------- demo guide (6 stories) ----------
const STORIES = [
  { title: "1 · New technician's first breakdown", ind: "factory", steps: [
    { t: "You are Arjun, a junior technician. Open <b>Live sensors</b> and press ▶ Play. Watch CNC-3.", go: "#/i/factory/technician/sensors", until: "alert" },
    { t: "CNC-3 crosses the limit. Press <b>Ask Ustaad what fixed this before</b>.", until: "asked" },
    { t: "First switch <b>Memory OFF</b> and ask again — generic chatbot advice. Then switch <b>Memory ON</b>: the proven fix, who did it, how much to trust it, sources — even from Pune's twin machine (🌐)." },
    { t: "Press <b>▶ Start guided mode</b>, tick each step, then tap <b>✔ Worked</b>. Ustaad learns and credits Ramesh." } ] },
  { title: "2 · Ramesh retires", ind: "factory", steps: [
    { t: "You are the supervisor. Open <b>Risk radar</b>: see what is only in Ramesh's head.", go: "#/i/factory/supervisor/risk" },
    { t: "Press <b>Start exit interview</b>. Answer one question (🎙️ voice works in Hindi) and save it." },
    { t: "Open <b>Approvals</b> and approve the new tip — it becomes trusted knowledge.", go: "#/i/factory/supervisor/approvals" },
    { t: "Open <b>Skill passport</b> for Ramesh: verified skills and how often others reused his fixes.", go: "#/i/factory/supervisor/passport" } ] },
  { title: "3 · Manager's Monday", ind: "factory", steps: [
    { t: "You are the plant head. Open <b>Impact & ₹</b>: time to fix, failed fixes and money, before vs after.", go: "#/i/factory/manager/stats" },
    { t: "In <b>Ask Ustaad</b>, ask: <i>Which machine lost the most downtime hours?</i> — you get a chart.", go: "#/i/factory/manager/ask", prefill: { asset_id: "CNC-1", problem: "Which machine lost the most downtime hours?", auto: true } },
    { t: "Open <b>Shift report</b> — built from records, sensor alerts and pending approvals.", go: "#/i/factory/manager/shift" },
    { t: "Open <b>Failure prediction</b> — trained on Microsoft's 100-machine dataset, with an honest note.", go: "#/i/factory/manager/fleet" },
    { t: "Open <b>SOP / playbook</b>, build one and press 🖨 Print / Save PDF.", go: "#/i/factory/manager/playbook" } ] },
  { title: "4 · Pune helps Bengaluru", ind: "factory", steps: [
    { t: "Ask about CNC-1's spindle orientation fault. Look for the 🌐 badge: Kavya fixed it at the Pune plant on the same model.", go: "#/i/factory/technician/ask", prefill: { asset_id: "CNC-1", problem: "CNC-1 spindle does not stop at orientation position on tool change", auto: true } },
    { t: "Press <b>ಕನ್ನಡ</b> to translate the answer to Kannada (needs the Groq key)." } ] },
  { title: "5 · Same engine, other industries", ind: "restaurant", steps: [
    { t: "Restaurant: ask why biryani rice turns mushy — Chef Joseph's fix, a failed attempt to avoid, Zomato evidence.", go: "#/i/restaurant/cook/ask", prefill: { asset_id: "BRY-2", problem: "Biryani rice is coming out mushy after we opened a new rice bag", auto: true } },
    { t: "Hospital: note the <b>no diagnosis</b> banner. Open the WHO <b>OT checklist</b>.", go: "#/i/healthcare/ot/checklist" },
    { t: "Hospital: ask about a ventilator alarm — Bengaluru's fix reaches Mysuru, plus real FDA reports.", go: "#/i/healthcare/nurse/ask", prefill: { asset_id: "VNT-M1", problem: "High blower temperature alarm on the ventilator at night", auto: true } },
    { t: "Garage: look up <b>P0171</b> — code meaning + Venki-anna's spray test.", go: "#/i/garage/mechanic/obd" },
    { t: "IT on-call: open the <b>Outage library</b> — 240 real public outages next to the team's own incidents.", go: "#/i/it/oncall/outages" },
    { t: "Try a 📷 photo question in <b>Ask Ustaad</b> (needs the Groq key).", go: "#/i/it/oncall/ask" } ] },
  { title: "6 · A new machine arrives", ind: "factory", steps: [
    { t: "You are the supervisor. Open <b>My machines</b> and press <b>＋ Add machine</b>.", go: "#/i/factory/supervisor/machines" },
    { t: "Upload the maker's <b>PDF manual</b> (or paste its web page, or snap the nameplate). Ustaad fills the form: specs, parts, known faults, service tasks. Give it an ID like <b>CNC-4</b> and press <b>Save</b>.", until: "machine" },
    { t: "This is the machine's page: health light, service due, spare parts, history, experts, manual — and a <b>QR sticker</b> to print and stick on it.", until: "profile" },
    { t: "Press <b>💬 Ask about CNC-4</b> and ask about an alarm from its manual — the answer comes from the 📘 maker's manual." },
    { t: "Tap <b>✖ Didn't work</b> or <b>✔ Worked</b> with what you really did. Ask again: now it says <b>Manual says … / team found …</b>. That's the whole idea." } ] },
];
const G = { open: false, s: 0, k: 0 };
function drawGuide() {
  const g = $("#guide"); if (!G.open) { g.classList.add("hidden"); return; } g.classList.remove("hidden");
  const st = STORIES[G.s], step = st.steps[G.k];
  g.innerHTML = `<div class="row" style="justify-content:space-between"><h3 style="margin:0">Demo guide</h3><button class="btn ghost sm" id="g-x">✕</button></div>
  <p class="tiny muted">6 short stories cover every feature. Follow the dark box.</p>
  ${STORIES.map((s, i) => `<div class="story ${i === G.s ? "on" : ""}" data-s="${i}"><b>${esc(s.title)}</b><div class="tiny muted">${s.steps.length} steps</div></div>`).join("")}
  <div class="stepnow"><div class="tiny" style="opacity:.7">Step ${G.k + 1} of ${st.steps.length}</div><p style="margin:6px 0 10px">${step.t}</p>
    <div class="row">${step.go ? '<button class="btn accent sm" id="g-go">Take me there</button>' : ""}<span style="flex:1"></span>
    <button class="btn sm" id="g-prev" ${G.k === 0 && G.s === 0 ? "disabled" : ""}>←</button><button class="btn sm" id="g-next">Next →</button></div></div>`;
  $("#g-x").onclick = () => { G.open = false; drawGuide(); };
  $$(".story", g).forEach((s) => (s.onclick = () => { G.s = +s.dataset.s; G.k = 0; drawGuide(); doStep(); }));
  if ($("#g-go")) $("#g-go").onclick = doStep;
  $("#g-prev").onclick = () => { if (G.k > 0) G.k--; else if (G.s > 0) { G.s--; G.k = STORIES[G.s].steps.length - 1; } drawGuide(); };
  $("#g-next").onclick = () => { if (G.k < st.steps.length - 1) G.k++; else if (G.s < STORIES.length - 1) { G.s++; G.k = 0; } else { toast("That's the whole tour 🎉"); } drawGuide(); doStep(); };
}
function doStep() { const step = STORIES[G.s].steps[G.k]; if (!step.go) return; if (step.prefill) S.prefill = { ...step.prefill }; go(step.go); }
function guideHook(event) {
  if (!G.open) return; const st = STORIES[G.s]; const step = st.steps[G.k];
  if (step.until === event && G.k < st.steps.length - 1) { G.k++; drawGuide(); }
}
$("#btn-guide").onclick = () => { G.open = !G.open; drawGuide(); };
$("#lang").innerHTML = Object.entries(LANGS).map(([k, v]) => `<option value="${k}">${v[0]}</option>`).join("");
$("#lang").onchange = (e) => { S.lang = e.target.value; store.set("ustaad-lang", S.lang); applyPrefs();
  toast(S.lang === "en" ? "English" : spin + " " + e.target.selectedOptions[0].text + (S.status?.sarvam ? " — Sarvam is translating the screen…" : " (needs the Sarvam key)"));
  route(); };
$("#btn-eng").onclick = () => { S.eng = !S.eng; store.set("ustaad-eng", S.eng ? "1" : "0"); applyPrefs();
  toast(S.eng ? "🔬 Engineer mode on — you'll see how every answer is made, IDs and the maths." : "Engineer mode off — simple view."); };
$("#btn-big").onclick = () => { S.big = !S.big; store.set("ustaad-big", S.big ? "1" : "0"); applyPrefs(); };
$("#fab-listen").onclick = listenScreen;

// ---------- router ----------
// ---------- 📢 morning briefing and 🎧 hands-free ----------
async function speakText(text, language) {
  if (!S.status?.sarvam) return false;
  const r = await api("/api/speak", { json: { text: text.slice(0, 2300), language: language === "hinglish" ? "hi" : language } });
  const au = new Audio(`data:${r.mime};base64,${r.audio}`); await au.play().catch(() => {});
  return new Promise((ok) => { au.onended = () => ok(true); au.onerror = () => ok(false); });
}
async function playBriefing(box) {
  box.innerHTML = `<div class="card">${spin} Getting today's briefing…</div>`;
  try { const b = await api(`/api/i/${S.ind}/briefing?language=${S.lang}`);
    box.innerHTML = `<div class="card brief"><b>📢 ${fmtDate(b.date)}</b><p style="margin:6px 0 0;font-size:15px">${esc(b.text)}</p>${S.status?.sarvam ? '<span class="tiny muted">🔊 playing…</span>' : '<span class="tiny muted">Add the Sarvam key to hear it.</span>'}</div>`;
    await speakText(b.text, S.lang); const t = $(".brief .tiny", box); if (t && S.status?.sarvam) t.textContent = "🔊 played"; }
  catch (e) { box.innerHTML = friendlyError(e, () => playBriefing(box)); bindRetry(box); }
}
function handsFree(assetId) {
  // one huge button: speak in your language -> Ustaad answers out loud in your language. For oily hands.
  const w = document.createElement("div"); w.className = "handsfree"; w.id = "handsfree";
  w.innerHTML = `<button class="btn sm hf-x" id="hf-x">✕ Close</button>
    <div class="hf-state" id="hf-state">Tap the button and say the problem</div>
    <button class="hf-btn" id="hf-btn"><span>🎙️</span><b>Tap and speak</b></button>
    <div class="hf-text" id="hf-text"></div>
    <div class="row hf-fb hidden" id="hf-fb"><button class="btn ok big" id="hf-ok">✔ It worked</button><button class="btn bad big" id="hf-no">✖ It didn't</button></div>`;
  document.body.appendChild(w); uiTranslate(w);
  const say = (t) => { $("#hf-state").textContent = t; };
  let last = null;
  $("#hf-x").onclick = () => w.remove();
  $("#hf-btn").onclick = (e) => toggleVoice(e.currentTarget, async (text) => {
    say("Looking through your team's experience…"); $("#hf-text").textContent = "“" + text + "”"; $("#hf-fb").classList.add("hidden");
    const language = S.lang !== "en" ? S.lang : (S.lastVoice?.language || "en");
    try {
      const r = await api(`/api/i/${S.ind}/ask`, { json: { asset_id: assetId || "ANY", problem: text, use_memory: true, language } }); last = r;
      const a = r.answer, first = a.check_first || (a.steps || [])[0] || a.summary;
      const rest = (a.check_first ? a.steps : (a.steps || []).slice(1)) || [];
      const spoken = [first, ...rest.slice(0, 3)].filter(Boolean).join(". ") + (a.safety ? ". " + a.safety : "");
      $("#hf-text").innerHTML = `<div class="hf-first">👉 ${esc(first)}</div>${rest.slice(0, 3).map((x, i) => `<div class="hf-step">${i + 2}. ${esc(x)}</div>`).join("")}${a.safety ? `<div class="safety">🦺 ${esc(a.safety)}</div>` : ""}`;
      say(S.status?.sarvam ? "🔊 Speaking…" : "Here's what to do");
      await speakText(spoken, language);
      say("Did it work? Or tap the button to ask again."); $("#hf-fb").classList.remove("hidden");
    } catch (err) { say(err.message); }
  });
  const fb = async (result) => { if (!last) return; try { const r = await api(`/api/i/${S.ind}/feedback`, { json: { ask_id: last.ask_id, result, person_id: S.person } });
    say(result === "fixed" ? "✔ Saved. Thank you — the next person gets your fix." : "✖ Saved. " + (r.expert ? `Call ${r.expert.name}.` : "")); $("#hf-fb").classList.add("hidden");
    speakText(result === "fixed" ? "Saved. Thank you." : (r.expert ? `Saved. Call ${r.expert.name}.` : "Saved."), S.lang); } catch (e) { say(e.message); } };
  $("#hf-ok").onclick = () => fb("fixed"); $("#hf-no").onclick = () => fb("failed_again");
}

// ---------- 📓 logbook pages and 🎥 fix videos ----------
async function logbookFlow(box, file) {
  box.innerHTML = `<div class="card">${spin} Reading the page${S.status?.sarvam ? " with Sarvam Vision" : ""}… (about 10–30 seconds)</div>`;
  const fd = new FormData(); fd.append("image", file); fd.append("language", S.lang);
  let r; try { r = await api(`/api/i/${S.ind}/logbook/read`, { method: "POST", body: fd }); } catch (e) { box.innerHTML = friendlyError(e, () => logbookFlow(box, file)); bindRetry(box); return; }
  const outc = (v) => Object.entries(OUTCOME).map(([k, l]) => `<option value="${k}" ${k === v ? "selected" : ""}>${l}</option>`).join("");
  box.innerHTML = `<div class="card" style="border-top:4px solid var(--accent)"><h3>📓 ${r.entries.length} entr${r.entries.length === 1 ? "y" : "ies"} found — check them, then save</h3>
    <p class="tiny muted">Read by ${esc(r.read_by)} · split by ${esc(r.written_by || "")}. Untick anything wrong. Saved entries wait for a senior's approval.</p>
    <div class="scroll"><table class="t lbt"><tr><th>✔</th><th>Date</th><th>${esc(L().asset)}</th><th>Problem</th><th>What was done</th><th>Result</th><th>Who</th></tr>
    ${r.entries.map((e, i) => `<tr data-i="${i}"><td><input type="checkbox" class="lb-on" ${e.asset_id ? "checked" : ""}></td><td><input class="field lb-d" type="date" value="${esc(e.date)}"></td>
      <td><select class="field lb-a"><option value="">— pick —</option>${assetOptions(e.asset_id)}</select></td><td><input class="field lb-p" value="${esc(e.problem)}"></td>
      <td><input class="field lb-x" value="${esc(e.action)}"><div class="tiny muted" title="What the page says">“${esc(e.line.slice(0, 90))}”</div></td><td><select class="field lb-o">${outc(e.outcome)}</select></td>
      <td><select class="field lb-w"><option value="">${esc(e.person_written || "—")}</option>${personOptions(e.person_id)}</select></td></tr>`).join("")}</table></div>
    <details><summary class="small">What the page says (raw text)</summary><pre class="pg-text">${esc(r.text)}</pre></details>
    <div class="row" style="margin-top:10px"><button class="btn accent big" id="lb-save">Save ticked entries to memory</button></div></div>`;
  $("#lb-save").onclick = async () => {
    const rows = $$(".lbt tr[data-i]", box).filter((tr) => $(".lb-on", tr).checked).map((tr) => { const e = r.entries[+tr.dataset.i];
      return { ...e, date: $(".lb-d", tr).value, asset_id: $(".lb-a", tr).value, problem: $(".lb-p", tr).value, action: $(".lb-x", tr).value, outcome: $(".lb-o", tr).value, person_id: $(".lb-w", tr).value }; });
    if (!rows.length) return toast("Tick at least one entry");
    if (rows.some((x) => !x.asset_id)) return toast(`Pick the ${L().asset.toLowerCase()} for every ticked entry`, "alert");
    try { const s2 = await api(`/api/i/${S.ind}/logbook/save`, { json: { entries: rows, person_id: S.person, page_ref: "Logbook page scanned " + new Date().toISOString().slice(0, 10) } });
      box.innerHTML = `<div class="card"><b>${esc(s2.message)}</b></div>`; } catch (e) { toast(esc(e.message), "alert"); }
  };
}
function wavBlob(samples, rate) {
  const b = new ArrayBuffer(44 + samples.length * 2), d = new DataView(b); const w = (o, s2) => [...s2].forEach((c, i) => d.setUint8(o + i, c.charCodeAt(0)));
  w(0, "RIFF"); d.setUint32(4, 36 + samples.length * 2, true); w(8, "WAVE"); w(12, "fmt "); d.setUint32(16, 16, true); d.setUint16(20, 1, true); d.setUint16(22, 1, true);
  d.setUint32(24, rate, true); d.setUint32(28, rate * 2, true); d.setUint16(32, 2, true); d.setUint16(34, 16, true); w(36, "data"); d.setUint32(40, samples.length * 2, true);
  for (let i = 0; i < samples.length; i++) { const v = Math.max(-1, Math.min(1, samples[i])); d.setInt16(44 + i * 2, v < 0 ? v * 0x8000 : v * 0x7fff, true); }
  return new Blob([b], { type: "audio/wav" });
}
async function splitVideo(file, say) {
  // the phone does the heavy part: a few photos + the sound as a small WAV (so a big video never has to be uploaded)
  const url = URL.createObjectURL(file); const v = document.createElement("video"); v.src = url; v.muted = true; v.playsInline = true; v.preload = "auto";
  try {
    await new Promise((ok, bad) => { v.onloadedmetadata = ok; v.onerror = () => bad(new Error("This video can't be opened here")); });
    const dur = Math.min(v.duration || 0, 180); if (!dur || !isFinite(dur)) throw new Error("Couldn't read the video length");
    const n = Math.min(8, Math.max(3, Math.round(dur / 10))), cv = document.createElement("canvas"), W = 480;
    cv.width = W; cv.height = Math.round(W * (v.videoHeight || 270) / (v.videoWidth || 480)); const frames = [];
    for (let i = 0; i < n; i++) { const t = dur * (i + 0.5) / n; v.currentTime = t; await new Promise((ok) => { v.onseeked = ok; setTimeout(ok, 3000); });
      cv.getContext("2d").drawImage(v, 0, 0, cv.width, cv.height); frames.push({ t: Math.round(t), blob: await new Promise((ok) => cv.toBlob(ok, "image/jpeg", 0.6)) }); say(`Took photo ${i + 1} of ${n}…`); }
    say("Taking out the sound…");
    const ac = new (window.AudioContext || window.webkitAudioContext)(); const audio = await ac.decodeAudioData(await file.arrayBuffer()); try { ac.close(); } catch { /* */ }
    const sec = Math.min(audio.duration, 180), off = new OfflineAudioContext(1, Math.ceil(16000 * sec), 16000);
    const src = off.createBufferSource(); src.buffer = audio; src.connect(off.destination); src.start(0);
    return { wav: wavBlob((await off.startRendering()).getChannelData(0), 16000), frames };
  } finally { URL.revokeObjectURL(url); }
}
async function videoFlow(box, file) {
  box.innerHTML = `<div class="card stack"><h3>🎥 Which ${esc(L().asset.toLowerCase())} is this video about?</h3><select id="vg-a" class="field">${assetOptions(S.lastAsk?.asset?.id)}</select>
    <button class="btn accent big" id="vg-go">Make the guide →</button><div class="tiny muted">${esc(file.name)} · ${(file.size / 1048576).toFixed(1)} MB · up to 3 minutes is used</div></div>`;
  $("#vg-go").onclick = async () => {
    const aid = $("#vg-a").value; const say = (t) => { box.innerHTML = `<div class="card">${spin} ${esc(t)}</div>`; };
    const fd = new FormData(); fd.append("asset_id", aid); fd.append("person_id", S.person); fd.append("language", S.lang);
    try { const sp = await splitVideo(file, say); fd.append("audio", sp.wav, "audio.wav"); sp.frames.forEach((f) => fd.append("frames", f.blob, `f_${f.t}.jpg`)); }
    catch (e) { if (file.size > 45 * 1048576) { box.innerHTML = `<div class="card"><b>This video is too big to send.</b><p class="small muted">Record a shorter one (under a minute), or try Chrome.</p></div>`; return; } fd.append("video", file, file.name); }
    say("Listening to what you said and writing the steps… (about 20–60 seconds)");
    let g; try { g = await api(`/api/i/${S.ind}/video-guide`, { method: "POST", body: fd }); } catch (e) { box.innerHTML = friendlyError(e, () => videoFlow(box, file)); bindRetry(box); return; }
    box.innerHTML = `<div class="card" style="border-top:4px solid var(--accent)"><label class="f">Title</label><input class="field" id="vg-t" value="${esc(g.title)}">
      ${g.summary ? `<p class="small">${esc(g.summary)}</p>` : ""}${g.safety ? `<div class="safety">🦺 ${esc(g.safety)}</div>` : ""}
      <ol class="vg-steps">${g.steps.map((s2, i) => `<li>${s2.image ? `<img src="${s2.image}" alt="">` : ""}<div><textarea class="field vg-s" data-i="${i}">${esc(s2.text)}</textarea><span class="tiny muted">at ${s2.at}s</span></div></li>`).join("")}</ol>
      <details><summary class="small">What was said</summary><pre class="pg-text">${esc(g.transcript)}</pre></details>
      <div class="tiny muted eng-only">Heard by ${esc(g.heard_by)} · steps by ${esc(g.written_by || "")}</div>
      <div class="row" style="margin-top:10px"><button class="btn accent big" id="vg-save">Save the guide</button><span class="small muted">Fix any step first — it goes into memory.</span></div></div>`;
    $("#vg-save").onclick = async () => { $$(".vg-s", box).forEach((t) => (g.steps[+t.dataset.i].text = t.value)); g.title = $("#vg-t").value;
      try { const r = await api(`/api/i/${S.ind}/guides`, { json: { guide: g, person_id: S.person } }); box.innerHTML = `<div class="card"><b>${esc(r.message)}</b> <a href="#" data-guide="${r.id}">Open it</a></div>`;
        $("[data-guide]", box).onclick = (e) => { e.preventDefault(); openGuide(r.id); }; } catch (e) { toast(esc(e.message), "alert"); } };
  };
}
async function loadGuides(box, aid) {
  try { const r = await api(`/api/i/${S.ind}/guides?asset_id=${encodeURIComponent(aid)}`); if (!r.guides.length) return;
    box.innerHTML = `<div class="card" style="margin-bottom:12px"><h3>🎥 Video guides</h3>${r.guides.map((g) => `<div class="li small"><a href="#" data-guide="${g.id}"><b>${esc(g.title)}</b></a> <span class="tiny muted">${g.steps} steps · ${esc(g.person)} · ${fmtDate(g.created)}</span></div>`).join("")}</div>`;
    $$("[data-guide]", box).forEach((x) => (x.onclick = (e) => { e.preventDefault(); openGuide(x.dataset.guide); })); } catch { /* none */ }
}
async function openGuide(gid) {
  $("#pg-drawer")?.remove(); const dr = document.createElement("div"); dr.id = "pg-drawer"; dr.className = "drawer"; dr.innerHTML = spin; document.body.appendChild(dr);
  try { const g = await api(`/api/i/${S.ind}/guides/${gid}`);
    dr.innerHTML = `<div class="row" style="justify-content:space-between"><b>🎥 ${esc(g.title)}</b><button class="btn sm" id="pg-x">✕</button></div><div class="tiny muted">${esc(g.asset_id)} · by ${esc(g.person)} · ${fmtDate(g.created)}</div>
      ${g.safety ? `<div class="safety">🦺 ${esc(g.safety)}</div>` : ""}<ol class="vg-steps view">${g.steps.map((s2) => `<li>${s2.image ? `<img src="${s2.image}" alt="">` : ""}<div>${esc(s2.text)}</div></li>`).join("")}</ol>
      <button class="btn sm no-print" onclick="window.print()">📄 Save as PDF</button>`;
    $("#pg-x").onclick = () => dr.remove(); uiTranslate(dr); } catch (e) { dr.innerHTML = `<p class="small" style="color:var(--bad)">${esc(e.message)}</p>`; }
}

// ---------- simple for everyone, deep for engineers ----------
S.lang = store.get("ustaad-lang") || "en"; S.eng = store.get("ustaad-eng") === "1"; S.big = store.get("ustaad-big") === "1";
function applyPrefs() {
  document.body.classList.toggle("eng", S.eng); document.body.classList.toggle("big", S.big);
  $("#btn-eng")?.classList.toggle("on", S.eng); $("#btn-big")?.classList.toggle("on", S.big);
  if ($("#lang")) $("#lang").value = S.lang; document.documentElement.lang = (LANGS[S.lang] || LANGS.en)[1].slice(0, 2);
}
// Welcome: first visit only — language first, then 3 pictures that explain everything
function welcome(force) {
  if (!force && store.get("ustaad-welcomed")) return;
  const w = document.createElement("div"); w.className = "welcome"; w.id = "welcome";
  w.innerHTML = `<div class="welcome-box">
    <div class="brand-w"><span class="dev">उस्ताद</span> Ustaad</div>
    <h2 style="margin:6px 0 2px">Your team's proven fixes — by voice, in your language.</h2>
    <p class="muted small">Choose your language:</p>
    <div class="langs" data-notr>${Object.entries(LANGS).map(([k, v]) => `<button class="langbtn ${k === S.lang ? "on" : ""}" data-l="${k}">${v[0]}</button>`).join("")}</div>
    <div class="how3">
      <div><span class="pic">🎙️</span><b>1. Say the problem</b><span class="small muted">Speak, type or take a photo.</span></div>
      <div><span class="pic">👷</span><b>2. Get your team's fix</b><span class="small muted">What worked before, and who did it.</span></div>
      <div><span class="pic">✅</span><b>3. Tap "It worked"</b><span class="small muted">The next person gets your fix.</span></div>
    </div>
    <button class="btn accent big" id="w-go" style="width:100%">Start →</button></div>`;
  document.body.appendChild(w);
  $$(".langbtn", w).forEach((b) => (b.onclick = () => { S.lang = b.dataset.l; store.set("ustaad-lang", S.lang); $$(".langbtn", w).forEach((x) => x.classList.toggle("on", x === b)); applyPrefs(); uiTranslate(w, true); }));
  $("#w-go").onclick = () => { store.set("ustaad-welcomed", "1"); w.remove(); route(); };
  uiTranslate(w);
}
// Screen labels in the chosen language (Sarvam translates each label once; it is remembered for everyone)
const UI_SEL = "h1,h2,h3,h4,label,button,button b,button span:not(.badge):not(.rec-dot),.help b,summary,th,td.muted,.help,.kpi span,.side a span,.crumbs a,.crumbs span,.crumbs b,p.muted,.small.muted,.tiny.muted,p.lead,.kicker,.step b,.step span,.how3 b,.how3 span,.badge:not(.mono),.chip span,a.btn,.empty-state b,.empty-state p,.doit-k,.fb-q,.usually,.sheet-item b,.sheet-item span,option.ui,.foot a,.foot span,.trust,.li b,.card > p,.hero p,.banner";
const UI_SKIP = ".mem,.mono,.ref,[data-tr],[data-notr],textarea,input,select,.pg-text,svg,pre,code,.lv-txt";
let _uiDict = {}, _uiLang = null, _uiBusy = null;
function uiDict(lang) { if (_uiLang !== lang) { _uiLang = lang; try { _uiDict = JSON.parse(store.get("ustaad-ui-" + lang) || "{}"); } catch { _uiDict = {}; } } return _uiDict; }
async function uiTranslate(root = document.body, restore = false) {
  const lang = S.lang, nodes = [];
  root.querySelectorAll(UI_SEL).forEach((el) => {
    if (el.closest(UI_SKIP)) return;
    el.childNodes.forEach((n) => { if (n.nodeType === 3) nodes.push(n); });
  });
  for (const n of nodes) { if (n._en === undefined) n._en = n.textContent; }
  if (lang === "en") { nodes.forEach((n) => { if (n._en !== undefined) n.textContent = n._en; }); return; }
  const want = nodes.filter((n) => { const t = n._en.trim(); return t.length >= 2 && t.length <= 160 && /[A-Za-z]{2}/.test(t) && !/^[A-Z0-9-]{2,12}$/.test(t) && !/^https?:/.test(t); });
  const dict = uiDict(lang);
  const missing = [...new Set(want.map((n) => n._en.trim()).filter((t) => !(t in dict)))];
  for (let i = 0; i < missing.length; i += 100) {
    try { const r = await api("/api/ui-translate", { json: { texts: missing.slice(i, i + 100), language: lang } });
      missing.slice(i, i + 100).forEach((t, j) => (dict[t] = r.texts[j])); } catch { break; }
  }
  try { store.set("ustaad-ui-" + lang, JSON.stringify(dict)); } catch { /* full */ }
  if (S.lang !== lang) return;
  want.forEach((n) => { const t = n._en.trim(); if (dict[t]) n.textContent = n._en.replace(t, dict[t]); });
}
let _uiTimer = null;
new MutationObserver(() => { if (S.lang === "en") return; clearTimeout(_uiTimer); _uiTimer = setTimeout(() => uiTranslate(app), 350); })
  .observe(document.getElementById("app"), { childList: true, subtree: true });
// 🔊 read this screen aloud (Sarvam Bulbul), for anyone who prefers listening
async function listenScreen() {
  const b = $("#fab-listen"); const panel = $("#panel") || app;
  const bits = [...panel.querySelectorAll(".help, h2, .trust, .doit, .ans-sum, .usually, #steps li, .card > p, .li b")].map((n) => n.innerText.trim()).filter(Boolean);
  const text = [...new Set(bits)].join(". ").slice(0, 900);
  if (!text) return toast("Nothing to read on this screen yet.");
  b.innerHTML = spin;
  try { const r = await api("/api/speak", { json: { text, language: S.lang === "hinglish" ? "hi" : S.lang } }); new Audio(`data:${r.mime};base64,${r.audio}`).play(); }
  catch (e) { toast(esc(e.message), "alert"); }
  b.textContent = "🔊";
}
// footer: proof for engineers, plain for everyone
function footer() {
  const ind = S.ind || "factory", role = S.role || (S.packs[ind]?.roles.find((r) => r.can_approve) || {}).id || "supervisor";
  return `<footer class="foot no-print"><span>Measured, not claimed:</span>
    <a href="#/i/${ind}/${role}/machines/accuracy">📏 Reader accuracy</a><a href="#/connect">🤖 Connect your AI</a><a href="#/system">⚙️ System</a><a href="#/api">{ } API</a>
    <a href="https://github.com/Anadijain1234/Plantmind/tree/main/tests" target="_blank" rel="noopener">🧪 Test suites</a>
    <a href="https://github.com/Anadijain1234/Plantmind" target="_blank" rel="noopener">GitHub</a>
    <a href="#" id="welcome-again">❓ How it works</a>${S.canInstall ? '<a href="#" id="install-app">📲 Install app</a>' : ""}</footer>`;
}
function alertHTML(al) {
  const who = al.expert, first = who ? who.name.split(" ")[0] : "";
  const wa = al.message ? `https://wa.me/${(al.phone || "").replace(/\D/g, "")}?text=${encodeURIComponent(al.message)}` : "";
  return `<div class="alertbar" data-al="${esc(al.id)}"><div class="al-main"><b>🚨 ${esc(al.asset_id)} is calling</b> — ${esc(al.what.toLowerCase())}, ${esc(al.value)}
      <span class="tiny">· ${al.minutes_ago < 1 ? "just now" : al.minutes_ago + " min ago"}</span>
      ${who ? `<div class="small">Best person: <b>${esc(who.name)}</b>${who.fixes ? ` — fixed this ${who.fixes} time${who.fixes === 1 ? "" : "s"}` : ""}${who.reused ? `${who.fixes ? "," : " —"} their fix reused ${who.reused}×` : ""}${al.last_fix ? ` · last time: <span data-tr>${esc(al.last_fix.action.slice(0, 90))}</span>` : ""}</div>` : ""}</div>
    <div class="row al-btns">${al.phone ? `<a class="btn sm" href="tel:${esc(al.phone)}">📞 Call ${esc(first)}</a>` : ""}${wa ? `<a class="btn sm ok" target="_blank" rel="noopener" href="${wa}">💬 WhatsApp ${esc(first)}</a>` : ""}
      <button class="btn sm" data-al-ask="${esc(al.asset_id)}" data-al-p="${esc(al.likely_problem || al.what)}">💬 Ask Ustaad</button><button class="btn sm" data-al-x="${esc(al.id)}" aria-label="Hide">✕</button></div></div>`;
}
async function alertBar() {
  if (!S.ind || !location.hash.startsWith("#/i/")) { $("#alerts")?.remove(); return; }
  let list = [];
  try { list = (await api(`/api/i/${S.ind}/alerts`)).alerts || []; } catch { return; }
  let hidden = []; try { hidden = JSON.parse(sessionStorage.getItem("ustaad-al-x") || "[]"); } catch { /* private window */ }
  list = list.filter((x) => !hidden.includes(x.id));
  let box = $("#alerts");
  if (!list.length) { box?.remove(); return; }
  if (!box) { box = document.createElement("div"); box.id = "alerts"; box.className = "no-print"; app.prepend(box); }
  box.innerHTML = list.slice(0, 3).map(alertHTML).join("");
  $$("[data-al-x]", box).forEach((b) => (b.onclick = () => { hidden.push(b.dataset.alX); try { sessionStorage.setItem("ustaad-al-x", JSON.stringify(hidden)); } catch { /* ok */ } b.closest(".alertbar").remove(); }));
  $$("[data-al-ask]", box).forEach((b) => (b.onclick = () => { S.prefill = { asset_id: b.dataset.alAsk, problem: `${b.dataset.alAsk}: ${b.dataset.alP} — the sensor alarm went off`, auto: true }; go(`#/i/${S.ind}/${S.role || roleObj()?.id}/ask`); }));
  if (S.lang !== "en") uiTranslate(box);
}
setInterval(() => { if (document.visibilityState === "visible") alertBar(); }, 60000);
function afterRender() {
  app.insertAdjacentHTML("beforeend", footer());
  alertBar();
  const wa = $("#welcome-again"); if (wa) wa.onclick = (e) => { e.preventDefault(); welcome(true); };
  const ia = $("#install-app"); if (ia) ia.onclick = async (e) => { e.preventDefault(); S.installEvt?.prompt(); };
  $("#fab-listen").classList.toggle("hidden", !S.status?.sarvam);
  if (S.lang !== "en") { uiTranslate(app); uiTranslate($(".topbar")); }
}
// 🤖 Connect your AI — both directions, in plain words
async function renderConnect() {
  const url = location.origin + "/mcp";
  const st = S.status || (await api("/api/status"));
  const ind = S.ind || "factory", eg = ind === "garage" ? ["PH-W", "check-engine light P0171"] : ["CNC-3", "alarm 2041 again"];
  const ais = [["Claude", "Add a custom connector and paste the link."],
    ["ChatGPT", "In the settings for connectors / plugins, choose “Add custom MCP server” and paste the link. (It may ask you to turn on developer mode.)"],
    ["Gemini", "Personal accounts: in Connected apps, add a custom MCP server and paste the link. Gemini Enterprise: your admin adds it."]];
  app.innerHTML = `<div class="crumbs"><a href="#/">Home</a> › <b>Connect your AI</b></div>
    <div class="panel-head"><div><h2>🤖 Connect your AI</h2><p class="muted small">Use your team's memory from inside ChatGPT, Claude or Gemini. Your AI asks Ustaad only what it needs for each question — the memory stays here.</p></div></div>
    <div class="card cx-link"><b>1. Copy this link</b>
      <div class="row" style="margin-top:8px;flex-wrap:nowrap"><input class="field mono" id="cx-url" value="${esc(url)}" readonly style="flex:1;min-width:0"><button class="btn accent" id="cx-copy">📋 Copy</button></div></div>
    <div class="grid g3" style="margin-top:12px">${ais.map(([n, how]) => `<div class="card"><b>2. In ${esc(n)}</b><p class="small" style="margin:6px 0 0">${esc(how)}</p></div>`).join("")}</div>
    <p class="tiny muted">Menus change often — if you can't find it, look for “Connectors” or “MCP” in your AI's settings.</p>
    <div class="card" style="margin-top:12px"><b>3. Then just ask in plain words</b>
      <ul class="small" style="margin:6px 0 0"><li>“Ask Ustaad: ${esc(eg[0])} has ${esc(eg[1])} — what should we check first, and who should I call?”</li>
        <li>“Using Ustaad, what needs attention today?”</li><li>“Who in our team has actually fixed a hydraulic leak?”</li></ul></div>
    <div class="card" style="margin-top:12px"><div class="row" style="justify-content:space-between"><b>✔ Test the connection</b><button class="btn" id="cx-test">▶ Run test</button></div>
      <ol class="small" id="cx-out" style="margin:8px 0 0"><li class="muted">Does the same 3 steps an AI does: say hello, read the menu, ask one question.</li></ol></div>
    <div class="card" style="margin-top:12px"><h3>Two directions — don't mix them up</h3>
      <div class="grid g2"><div><b>🤖 → 🧠 Your AI uses Ustaad</b><p class="small">This page. ChatGPT / Claude / Gemini asks Ustaad's memory and writes the answer itself. Works through the link above (MCP).</p></div>
      <div><b>🧠 → 🤖 Ustaad uses your AI</b><p class="small">Who writes Ustaad's own answers. Right now: <b>${esc((st.writers || []).join(" → ") || "rules (no AI key)")}</b>. A company that must use its own AI can switch it in the server settings — memory, maths and Kannada voice stay the same.</p>
        <details class="eng-only small"><summary>How (server settings on Render)</summary><pre class="pg-text">BRAIN_URL   = https://api.openai.com/v1      (or Gemini's / your own server's address)
BRAIN_KEY   = the key from that AI
BRAIN_MODEL = the model name, e.g. gpt-4o-mini
BRAIN_NAME  = how the app shows it, e.g. ChatGPT</pre><p class="tiny muted">Any AI that accepts OpenAI-style requests works: OpenAI, Gemini, Claude, or a company's own model run with Ollama / vLLM. Remove the settings to go back to Sarvam.</p></details></div></div></div>
    <div class="card eng-only" style="margin-top:12px"><h3>Tools your AI gets</h3><div id="cx-tools" class="small">${spin}</div>
      <p class="tiny muted">Also: every machine as a file, e.g. <a href="/machines/factory/CNC-3.md" target="_blank">/machines/factory/CNC-3.md</a> · <a href="/llms.txt" target="_blank">/llms.txt</a> · <a href="#/api">{ } API</a>.
      This demo link is open (sample data). For a real company, the server is locked with MCP_TOKEN and a sign-in step is added.</p></div>`;
  $("#cx-copy").onclick = async () => { try { await navigator.clipboard.writeText(url); toast("Copied — now paste it in your AI."); } catch { $("#cx-url").select(); toast("Select and copy the link."); } };
  const rpc = async (id, method, params) => {
    const t = performance.now(); const r = await fetch("/mcp", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ jsonrpc: "2.0", id, method, params }) });
    return { j: await r.json(), ms: Math.round(performance.now() - t) };
  };
  rpc(0, "tools/list", {}).then(({ j }) => { $("#cx-tools").innerHTML = (j.result?.tools || []).map((x) => `<div style="margin:4px 0"><b class="mono">${esc(x.name)}</b> — ${esc(x.description)}</div>`).join(""); }).catch(() => {});
  $("#cx-test").onclick = async () => {
    const o = $("#cx-out"); o.innerHTML = `<li>${spin} Saying hello…</li>`;
    try {
      const a = await rpc(1, "initialize", { protocolVersion: "2025-06-18", capabilities: {}, clientInfo: { name: "ustaad-test", version: "1" } });
      o.innerHTML = `<li>✔ Hello — connected to <b>${esc(a.j.result.serverInfo.title)}</b> <span class="tiny muted">${a.ms} ms</span></li><li>${spin} Reading the menu…</li>`;
      const b = await rpc(2, "tools/list", {});
      o.lastElementChild.outerHTML = `<li>✔ Menu — <b>${b.j.result.tools.length} tools</b> <span class="tiny muted">${b.ms} ms</span></li><li>${spin} Asking one question…</li>`;
      const c = await rpc(3, "tools/call", { name: "search_memory", arguments: { industry: ind, machine_id: eg[0], problem: eg[1] } });
      const d = JSON.parse(c.j.result.content[0].text); const m = d.memories?.find((x) => x.outcome === "fixed") || d.memories?.[0];
      o.lastElementChild.outerHTML = `<li>✔ Asked “${esc(eg[0])}: ${esc(eg[1])}” — <b>${d.memories.length} past cases</b> came back${m ? `, e.g. ${esc(m.person || "")} · ${esc(m.action || "").slice(0, 70)}${m.outcome === "fixed" ? " ✔ worked" : ""}` : ""} <span class="tiny muted">${c.ms} ms</span></li>
        <li><b>🎉 Works.</b> Any AI that supports MCP can now use this link.</li>`;
    } catch (e) { o.innerHTML += `<li>✖ ${esc(e.message)} — if the server was asleep, wait a minute and run it again.</li>`; }
  };
}
// ⚙️ System page — what is running right now
async function renderSystem() {
  const d = await api("/api/system"), st = d.status;
  const dot = (ok) => `<span class="badge ${ok ? "b-verified" : "b-unreviewed"}">${ok ? "● on" : "● off"}</span>`;
  app.innerHTML = `<div class="crumbs"><a href="#/">Home</a> › <b>System</b></div>
    <div class="panel-head"><div><h2>⚙️ System</h2><p class="muted small">Live state of everything Ustaad uses. For engineers and judges.</p></div></div>
    <div class="grid g3">
      <div class="card"><h3>Services</h3><table class="t">
        <tr><td>Memory</td><td>${esc(st.memory)} ${dot(st.memory.startsWith("Hindsight"))}</td></tr>
        <tr><td>Writes the answers</td><td class="small">${esc((st.writers || []).join(" → ") || "rules (no AI key)")}${st.own_brain ? ' <span class="badge b-src">your own AI</span>' : ""}</td></tr>
        <tr><td>Sarvam (writes, voice, translate, OCR)</td><td>${dot(st.sarvam)}</td></tr><tr><td>Groq (backup writer)</td><td>${dot(st.groq)}</td></tr>
        <tr><td>Auto-save to GitHub</td><td>${dot(st.autosave?.enabled && st.autosave?.ready)} <span class="tiny muted">${esc(st.autosave?.last_saved || "")}</span></td></tr>
        <tr><td>Voice order</td><td>${esc((d.voice.order || []).join(" → ") || "—")} ${d.voice.ffmpeg ? '<span class="tiny muted">· ffmpeg ✓</span>' : ""}</td></tr></table></div>
      <div class="card"><h3>Models</h3><table class="t">${Object.entries(d.models).map(([k, v]) => `<tr><td class="small muted">${esc(k.replace(/_/g, " "))}</td><td class="small mono">${esc(v)}</td></tr>`).join("")}</table></div>
      <div class="card"><h3>Runtime</h3><table class="t">${Object.entries(d.runtime).map(([k, v]) => `<tr><td class="small muted">${esc(k.replace(/_/g, " "))}</td><td class="small mono">${esc(v || "—")}</td></tr>`).join("")}</table>
        <p class="small" style="margin-top:8px">🧪 Offline test suites: ${d.tests.map((t) => `<span class="badge b-src mono">${esc(t)}</span>`).join(" ")}</p></div></div>
    <div class="card" style="margin-top:14px"><h3>How a question flows</h3><div class="flow">
      ${["🎙️ Voice → Sarvam Saaras (Google, Groq backup)", "🌐 Indian language → Sarvam translates to English", "🧠 Hindsight: search near the machine + the whole team", "📊 Re-rank by codes & words", "✍️ Sarvam writes (Groq backup); must name the memories it used", "🎯 Cause % + smartest order (maths, no AI)", "🌐 Sarvam translates back · 🔊 Bulbul reads it", "✅ Worked / Didn't work → new memory"].map((x) => `<span>${esc(x)}</span>`).join("<b>→</b>")}</div></div>
    <div class="card" style="margin-top:14px"><h3>Data per industry</h3><table class="t"><tr><th>Industry</th><th>Records</th><th>Machines</th><th>Memory bank</th></tr>
      ${Object.entries(d.data).map(([k, v]) => `<tr><td>${esc(k)}</td><td>${v.records}</td><td>${v.machines}</td><td class="mono small">${esc(v.bank)}</td></tr>`).join("")}</table></div>`;
}
// { } API page — every endpoint, with a copy-ready example
async function renderApiPage() {
  const d = await api("/api/endpoints"); const host = location.origin;
  const ex = { "/api/i/<industry>/ask": `curl -s ${host}/api/i/factory/ask -H "Content-Type: application/json" -d '{"asset_id":"CNC-3","problem":"alarm 2041 whistling","language":"hi"}'`,
    "/api/i/<industry>/sensors/reading": `curl -s ${host}/api/i/factory/sensors/reading -H "Content-Type: application/json" -d '{"asset_id":"CNC-3","vib":5.2,"temp":71,"hours":12850}'`,
    "/api/voice": `curl -s ${host}/api/voice -F audio=@question.webm -F language=kn -F industry=factory`,
    "/api/i/<industry>/machines/read": `curl -s ${host}/api/i/factory/machines/read -H "Content-Type: application/json" -d '{"url":"https://example.com/product"}'` };
  app.innerHTML = `<div class="crumbs"><a href="#/">Home</a> › <b>API</b></div>
    <div class="panel-head"><div><h2>{ } API</h2><p class="muted small">${d.endpoints.length} endpoints. A sensor gateway, a WhatsApp bot or another AI can use Ustaad directly.</p></div></div>
    <div class="card" style="margin-bottom:10px;border-top:4px solid var(--accent)"><h3>🤖 For other AIs</h3>
      <p class="small">Ustaad is an <b>MCP server</b>: any AI assistant that supports MCP can ask the plant's memory directly — 7 tools: ask_ustaad, search_memory, list_machines, machine_summary, cause_chances, find_expert, morning_briefing. <a href="#/connect"><b>Step-by-step: Connect your AI →</b></a></p>
      <pre class="pg-text">${esc(JSON.stringify({ mcpServers: { ustaad: { type: "http", url: host + "/mcp" } } }, null, 2))}</pre>
      <p class="small">Every machine is also a readable file, e.g. <a href="/machines/factory/CNC-3.md" target="_blank">/machines/factory/CNC-3.md</a> · index for AIs: <a href="/llms.txt" target="_blank">/llms.txt</a></p>
      <pre class="pg-text">${esc(`curl -s ${host}/mcp -H "Content-Type: application/json" -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"cause_chances","arguments":{"industry":"factory","machine_id":"CNC-3","problem":"alarm 2041"}}}'`)}</pre></div>
    ${Object.entries(ex).map(([k, v]) => `<div class="card" style="margin-bottom:10px"><b class="mono">${esc(k)}</b><pre class="pg-text" style="margin:6px 0 0;overflow-x:auto">${esc(v)}</pre></div>`).join("")}
    <div class="card"><table class="t"><tr><th>Method</th><th>Path</th><th>What it does</th></tr>${d.endpoints.map((e) => `<tr><td class="mono small">${e.methods.join(", ")}</td><td class="mono small">${esc(e.path)}</td><td class="small">${esc(e.doc)}</td></tr>`).join("")}</table></div>`;
}
// installable app
if ("serviceWorker" in navigator) { window.addEventListener("load", () => navigator.serviceWorker.register("/sw.js").catch(() => {})); }
window.addEventListener("beforeinstallprompt", (e) => { e.preventDefault(); S.installEvt = e; S.canInstall = true; });

async function route() {
  clearCharts(); $("#pg-drawer")?.remove();
  const h = location.hash.replace(/^#\/?/, ""); const parts = h.split("/").filter(Boolean);
  try {
    if (parts[0] === "m" && parts[2]) { await openFromQR(parts[1], decodeURIComponent(parts[2])); return; }
    if (parts[0] === "i" && parts.length >= 4) await renderWorkspace(parts[1], parts[2], parts[3], parts[4]);
    else if (parts[0] === "i" && parts[1]) await renderRoles(parts[1]);
    else if (parts[0] === "passport") await renderPassportPage(parts[1], parts[2], parts[3]);
    else if (parts[0] === "system") await renderSystem();
    else if (parts[0] === "api") await renderApiPage();
    else if (parts[0] === "connect") await renderConnect();
    else await renderHome();
  } catch (e) { app.innerHTML = friendlyError(e, route); bindRetry(app); }
  afterRender();
  window.scrollTo(0, 0);
}
window.addEventListener("hashchange", route);
applyPrefs(); welcome();
loadStatus().then(() => $("#fab-listen").classList.toggle("hidden", !S.status?.sarvam)); route();
