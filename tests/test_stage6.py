"""Stage 6, offline: who writes (Sarvam first, Groq backup, your own AI), other plants, the machine calls first, MCP search.
Run:  python tests/test_stage6.py"""
import json
import os
import sys
import tempfile
from pathlib import Path

for _k in ("HINDSIGHT_API_KEY", "GROQ_API_KEY", "SARVAM_API_KEY", "GITHUB_TOKEN", "GITHUB_REPO", "BRAIN_URL", "BRAIN_KEY", "BRAIN_MODEL"):
    os.environ[_k] = ""
os.environ["DB_PATH"] = str(Path(tempfile.mkdtemp()) / "test.db")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import app as A  # noqa: E402
from ustaad import config, llm, logs, network, packs, store  # noqa: E402

C = A.app.test_client()


def test_writer_order():
    keep = (config.SARVAM_API_KEY, config.GROQ_API_KEY, config.WRITER, config.BRAIN_URL, config.BRAIN_MODEL, llm._sarvam_json, llm._groq_json, llm._custom_json)
    try:
        config.SARVAM_API_KEY, config.GROQ_API_KEY, config.WRITER = "k", "k", "sarvam"
        assert [n for n, _ in llm.writers()] == ["Sarvam", "Groq"]
        calls = []
        llm._sarvam_json = lambda *a, **k: calls.append("sarvam") or {"summary": "from sarvam"}
        llm._groq_json = lambda *a, **k: calls.append("groq") or {"summary": "from groq"}
        assert llm.chat_json("s", "u")["summary"] == "from sarvam" and llm.last_provider == "Sarvam" and calls == ["sarvam"]
        llm._sarvam_json = lambda *a, **k: calls.append("sarvam") or None  # Sarvam slow / down -> Groq writes
        assert llm.chat_json("s", "u")["summary"] == "from groq" and llm.last_provider == "Groq (backup)"
        config.WRITER = "groq"
        assert [n for n, _ in llm.writers()] == ["Groq", "Sarvam"]
        config.BRAIN_URL, config.BRAIN_MODEL = "https://example.com/v1", "my-model"  # bring your own brain: it writes first
        llm._custom_json = lambda *a, **k: {"summary": "from own"}
        assert llm.writers()[0] == ("Your own AI", "my-model") and llm.chat_json("s", "u")["summary"] == "from own"
        assert llm.last_provider == "Your own AI"
    finally:
        (config.SARVAM_API_KEY, config.GROQ_API_KEY, config.WRITER, config.BRAIN_URL, config.BRAIN_MODEL,
         llm._sarvam_json, llm._groq_json, llm._custom_json) = keep


def test_other_plants():
    a = C.post("/api/i/factory/ask", json={"asset_id": "CNC-3", "problem": "alarm 2041 whistling at high rpm"}).get_json()
    o = a["other_plants"]
    assert o and o["match"] == "the same HMC-500" and o["sample"] is True
    assert "coupling" in o["fixes"][0]["fix"].lower() and o["fixes"][0]["worked"] >= 10
    assert C.post("/api/i/it/ask", json={"asset_id": "PG-2", "problem": "too many clients"}).get_json()["other_plants"] is None
    # sharing: names, company and places are removed before anything leaves the plant
    s = network._scrub("factory", "Ramesh-ji realigned it at Kaveri Precision Components, Peenya")
    assert "Ramesh" not in s and "Kaveri" not in s and "Peenya" not in s, s
    r = C.post("/api/i/factory/feedback", json={"ask_id": a["ask_id"], "result": "fixed", "person_id": "ramesh"})
    assert r.status_code == 200 and C.get("/api/i/factory/network/settings").get_json()["shared"] >= 1
    assert C.post("/api/i/factory/network/settings", json={"share": False}).get_json()["share"] is False


def test_machine_calls_first():
    r = C.post("/api/i/factory/sensors/reading", json={"asset_id": "CNC-3", "vib": 7.0, "temp": 45}).get_json()
    plan = r["alert"]["plan"]
    assert plan["expert"] and plan["likely_problem"] == "Spindle vibration" and "Ustaad alert" in plan["message"]
    al = C.get("/api/i/factory/alerts").get_json()["alerts"]
    assert al and al[0]["asset_id"] == "CNC-3" and al[0]["expert"]["name"]
    b = C.get("/api/i/factory/briefing").get_json()
    assert b["items"][0]["kind"] == "alert" and "CNC-3 called" in b["text"]


def test_mcp_search_memory_and_logs():
    m = C.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}).get_json()
    assert "search_memory" in [t["name"] for t in m["result"]["tools"]]
    m = C.post("/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "search_memory",
               "arguments": {"industry": "factory", "machine_id": "CNC-3", "problem": "spindle vibration"}}}).get_json()
    d = json.loads(m["result"]["content"][0]["text"])
    assert d["memories"] and d["memories"][0]["outcome"] and d["other_plants"]
    assert logs.clean("tools/call ask_ustaad ok") == "tools/call ask_ustaad ok"
    fake = "gsk" + "_" + "notarealkey" + "0" * 6  # built in pieces so no key-shaped text sits in the code
    assert fake not in logs.clean("key " + fake) and "secret" not in logs.clean("Bearer secret123")


if __name__ == "__main__":
    test_writer_order(); test_other_plants(); test_machine_calls_first(); test_mcp_search_memory_and_logs()
    print("All Stage 6 tests passed.")
