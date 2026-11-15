# Ustaad — cheat sheet (explain it in your own words)

**One line:** When your best expert leaves, their know-how shouldn't. Ustaad remembers what the senior people did and whether it worked, gives it to the next person at the right moment, and gets better every time someone taps *worked* or *didn't work*.

**The analogy:** A new cricketer has a senior player standing next to him who remembers every match: "last time this bowler did this, this shot worked, that one got me out." Ustaad is that senior for a factory, kitchen, hospital, garage or IT team.

---

## The 3 flows you must be able to explain

**1. How a memory is saved**
A worker says or types what happened ("CNC-3 whistling, realigned the coupling, fixed in 40 minutes"). The AI turns it into a clean record: machine, problem, cause, action, result. It is saved twice:
- into **Hindsight**, the memory that understands meaning and can search it;
- into a small local database (the "scorebook") that keeps exact numbers for charts.

It shows as **Unreviewed** until a senior approves it.

**2. How an answer is made**
1. A worker asks a question.
2. **Hindsight recall** searches the memory twice: once near this machine and its twins, and once across the whole industry.
3. **A second check** re-ranks the results. Memories that share the alarm code or the same words go to the top. "Same machine, different problem" memories drop.
4. **Sarvam-105B** (the AI; Groq is the backup) gets those memories and must first say which ones are about the *same* problem. Then it writes the answer: check first, the steps, what NOT to repeat, who did it and when.
5. The green or orange banner counts only the memories it actually used.

If nothing matches, it says honestly: "New problem — nothing in your team's memory."

This is RAG. Hindsight is the "look things up" part and Sarvam (or Groq as backup) is the "write the answer" part.

**3. How it learns**
After the fix the worker taps **✔ Worked** or **✖ Didn't work**. That result becomes a new memory.
- Fixes that keep working rise and get the **Verified** tag.
- Fixes that failed show up in "Don't repeat".
- The expert whose fix was reused gets credit on their **skill passport**.
- If it didn't work, Ustaad says who to call and opens WhatsApp with the message ready.

---

## Every feature in one line

| Feature | One line |
|---|---|
| Ask Ustaad | Describe a problem by typing, voice or photo, and get your team's proven fix with who did it and when. |
| Memory ON / OFF | OFF is a normal chatbot; ON is your team's real history. This shows why memory matters. |
| Trust tags | ✔ Verified (worked 2+ times), Tested once, Unreviewed, ✖ Didn't work, Public record, 📘 Maker's manual, 🧠 Hindsight pattern, 📡 Sensor-confirmed. |
| Not sure which machine | The worker doesn't have to pick one; Ustaad searches everything. |
| I fixed something | Say what you did in any language; it becomes a memory. |
| Approvals | A senior checks new knowledge before it counts as trusted. |
| Flag as wrong | A bad memory gets flagged and Ustaad stops using it. |
| Voice | Speak in any Indian language, even mixed. It stops by itself when you pause. Sarvam hears first (it knows your machine names and codes), then Google, then Groq. |
| 12 languages | The answer is written in English, and Sarvam translates it. Memory stays in English, so a fix said in Kannada is found by a question in Hindi. 🔊 reads the answer aloud. |
| Sarvam Vision OCR | Scanned manual pages, nameplates and alarm-screen photos are read by Sarvam Vision, which is built for Indian scripts, tables and handwriting. |
| **My machines** | Every machine in one place, with a health light, service due, spare parts, warranty, history, experts and manual. |
| Add from manual / website / nameplate | Upload any PDF, paste any link or snap the nameplate. Ustaad finds the useful pages, identifies the exact model and fills the right fields for that kind of machine. |
| 🟢🟠🔴 checked fields | Code checks every value against the source. 🟢 means found, 🟠 means check it, 🔴 means it looks wrong. Units are converted, e.g. 15 hp = 11.2 kW. "The AI can't sneak a made-up number in." |
| Model picker | One brochure covers 4 models? Ustaad asks "which one is yours?" and fills that model's row. |
| Ask the manual | A question box on the machine page. It answers only from that machine's manual, with the page number. |
| 🧠 Expert report | Ustaad reads the manual like a senior engineer of that field: what breaks first and why, the full maintenance plan, spares to keep, and what the manual doesn't say. 📘 means the quote is on that page (code checks it); 🧠 means an expert conclusion. |
| 🧩 Profile & parts | One standard profile for every machine (5 layers, ISO 14224), a part tree with a page for every part, a completeness %, and "Ask the vendor" for what's missing. |
| 📄 Page beside the answer | Tap any page number and that manual page opens next to you with the quote highlighted. |
| 🔌 Drawing search | "Where is relay K1?" finds it on the wiring drawings. 📷 A photo of a panel finds its pages. |
| 🎯 Cause % | "Coupling 74%, bearing 16%." This is calculated from your own team's past cases (same machine, same model, same type), with newer cases counting more. It's conditional probability on real data. |
| 🧠 Smartest check first | Check the cause with the best chance *per minute* first. That gives the shortest average time to find the problem. |
| ⏳ Memory aging | Old fixes that were never re-confirmed, or that failed since, lose trust automatically. |
| 💸 Cost of not asking | "The fix was already in memory, but a bearing was swapped first: 10 h and ₹1.28 lakh lost." |
| 🔍 Pattern detective | A timeline that finds rhythms, like "comes back every 49 days" or "after the spider was replaced it stayed away 83 days". |
| ⏱️ Uptime + stops | Log why a machine stopped. Uptime % and lost hours are shown by reason. |
| ⚙️ Part life by hours | "1,900 of 2,000 h used." Part life comes from the hour meter, not just the calendar. |
| 📓 Logbook scanner | Photograph an old handwritten register. Every line becomes a memory, after a senior approves it. |
| 🎥 Video → guide | Film a fix while explaining it. You get steps with a photo for each step, in the worker's own words. |
| 🧓 Ask Ramesh | Answers only from one expert's own fixes. Ramesh retires, his know-how stays. |
| 🎓 Manual quiz + 🛡️ safety check | 5 questions from the machine's own manual. Risky steps stay locked until the safety checks are ticked. |
| 🔎 Who can fix this? | People ranked by proof, not job title. "⚠ 1 person" marks where only one person knows a machine. |
| 🎧 Hands-free mode | One huge button. Speak in Kannada, hear the answer in Kannada. Then ✔ / ✖. For oily hands. |
| 📢 Morning briefing | 30 seconds, spoken, in your language: what's due today, what's out of stock, what broke yesterday. |
| 🤖 Ustaad for other AIs | An MCP server at /mcp + one .md file per machine + /llms.txt. Any AI assistant can ask the plant's memory. |
| 🏭 The machine calls first | A sensor crosses its limit → the case opens by itself, a red bar shows on every screen with the best person to call and what worked last time. |
| 🌐 Other plants | Under the answer: what worked for the same problem on the same model in other plants. Names and companies hidden. Sample data in the demo. |
| 🤖 Connect your AI | Copy one link into ChatGPT / Claude / Gemini. Your AI asks Ustaad's memory; the memory stays with us. Test button included. |
| 🧠 Bring your own brain | Sarvam writes by default. A company that must use its own AI changes 4 server settings; memory, maths and voice stay the same. |
| 📜 Clear logs | Every feature writes one line in the Render logs ([ASK], [AI], [MEMORY], [MCP]…). Search FAILED to find problems. Keys are never written. |
| 🏅 Proof-backed passport | Every skill links to the real fixes that prove it. There's a skill graph, a private share link and a PDF. |
| 📅 Calendar | Service dates go to your phone calendar, with a reminder one day before. |
| 📏 Reader accuracy | Real maker documents with answers checked by hand. Ustaad's reading is scored, and wrong answers show too. |
| Manual says vs team found | The answer shows when the team's real fix differs from the official manual. |
| QR sticker | Like a DMart barcode: stick it on the machine, scan it with a phone, and Ustaad opens with that machine picked. |
| Service due | "Coupling spider: 4 days overdue". The last replacement date comes from the repair history. |
| Spare parts | "0 in store, order now" shows in answers; replacing a part in a log reduces the stock. |
| Sensor auto-log | A sensor crosses its limit, so Ustaad writes half the log itself; normal readings after the fix mean "Sensor-confirmed". |
| Ask the expert | A fix failed, so Ustaad names who fixed it before and drafts a WhatsApp message. |
| SOP / playbook | A printable procedure built only from fixes that worked. |
| Risk radar | "If Ramesh leaves, these fixes leave with him." |
| Exit interview | Questions for a leaving expert, only about things nobody wrote down. |
| Skill passport | Proof of a person's skills, built from fixes that worked. |
| Shift report | A handover note from real records, sensor alerts and out-of-stock parts. |
| ROI dashboard | Downtime hours saved, repeat failures avoided, fixed vs failed, ₹ saved, before vs after. |
| Knowledge coverage | Each machine scored /100 for how much of its know-how is captured; red flag when only one person knows it. |
| Expert leaderboard | Points for fixes that worked and fixes others reused, plus badges. Credit drives sharing. |
| Quiz | New joiners learn from the team's own past problems. |
| Failure prediction | A model trained on Microsoft's public 100-machine data says *when*; Ustaad's memory says *what to do*. |
| Build your own industry | Type "bakery" and Ustaad creates the roles and equipment; memory starts empty and learns. |
| 💾 Auto-save | Everything added on the site is saved to our GitHub repo and comes back after a restart or redeploy. |
| Off-topic guard | "Capital of France?" or a medicine dose gets "Outside what Ustaad answers". |

---

## The design idea in one line
**Simple on the surface, deep underneath.** A carpenter sees "What's wrong?", a big mic button, "👉 Do this first" and "✔ Yes, it worked", all in his language. An engineer taps 🔬 and sees every step with its time, the maths, the system page and the API.

## MCP vs "bring your own brain" — opposite directions

- **MCP (Connect your AI):** the manager stays in ChatGPT. ChatGPT *asks Ustaad* for the few memories it needs for that one question, then writes the answer. Ustaad is the library; ChatGPT is a tutor who phones the library.
- **Bring your own brain:** the worker stays in Ustaad. Ustaad *asks a different AI* to write its own answers (Sarvam by default). Only the writer changes — the library, the maths and the Kannada voice stay.

## Questions a judge may ask

- **What is Hindsight?** An agent-memory service by Vectorize. We use its 4 calls:
  - `create_bank`: one memory bank per industry;
  - `retain`: save a memory;
  - `recall`: search memories by meaning;
  - `reflect`: reason over many memories, used to build SOPs.

  It also learns **patterns** by itself, which we show as "🧠 Pattern Hindsight learned".
- **Why two stores (Hindsight + SQLite)?** Hindsight understands and searches meaning. SQLite keeps exact numbers for charts, trust counts, approvals and stock. It's like a brain plus a notebook.
- **Doesn't free hosting lose data on every deploy?** Knowledge is safe in Hindsight. The notebook part (machines, stock, approvals) is **auto-saved** a few seconds after every change to one file on a separate branch of our GitHub repo, and loaded back when the server starts (the 💾 chip). If GitHub can't be reached at start, saving pauses, so good data is never overwritten.
- **Is the data real?** The people and companies are fictional. The facts and public data are real:
  - FDA device reports, NHTSA car complaints, NYC kitchen inspections, Zomato reviews;
  - 240 public outage write-ups, Microsoft and AI4I machine datasets;
  - real maker manuals.

  Spare-part stock and warranty dates are demo data, and they are marked as demo on screen.
- **The model scores AUC 1.0. Is that cheating?** No. Microsoft generated that dataset for a tutorial, so its signals are cleaner than any real plant. We checked for data leakage (none found), and we say this on screen.
- **Why Sarvam and Groq both?** Sarvam writes the answers and does everything Indian-language: voice, translation, reading scans. Groq (fastest in the world at this) is the backup writer. The answer is written in English first so memory stays in one language and codes like "CNC-3" stay safe, then Sarvam translates.
- **Groq or Grok?** Groq (with a q) is a company with very fast chips; it runs OpenAI's free gpt-oss-120b model for us. Grok is a different thing — xAI's chatbot.
- **Is it heavy?** No. Our server is a small Flask app. Hindsight (memory) and Groq/Sarvam (AI) are services, so each question makes about 3 API calls. If Sarvam fails, Groq takes over. If both fail, a rule-based answer still works.
- **How does it scale?** A new company is a new Hindsight bank. A new industry is one JSON file. The server keeps no state between requests, so you can run more copies. For real customers, move SQLite to Postgres.
- **How does it read any PDF?** In three passes: find, understand, check.
  - **Find:** Python reads every page and keeps the useful ones (specs, alarms, parts, warranty). Tables are read cell by cell, and pictures of pages go to a vision AI.
  - **Understand:** the AI names the model and fills the fields, with an exact quote for each.
  - **Check:** code, not AI, confirms every value appears in the document and converts the units.

  A 211-page manual takes about 3 seconds before the AI step.
- **How is the 74% calculated?** We count how often each cause really fixed this problem on this machine, its twins and same-type machines, give newer cases more weight, and keep a small share for "something else". It's Bayesian smoothing, and the smartest order sorts by chance ÷ minutes.
- **Can it be wrong?** Yes. That's why every field has a colour, and why there is a public accuracy page instead of a claim.
- **What's next?** Offline mode for low-network shop floors, a WhatsApp bot, and a quiz from a new machine's manual.
