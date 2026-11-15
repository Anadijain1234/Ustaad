"""
Ustaad as an MCP server, so any AI assistant (Claude, ChatGPT, a plant's own bot) can ask the plant's memory directly.
Transport: MCP "Streamable HTTP" — JSON-RPC 2.0 over POST /mcp, answered as plain JSON.
Optional protection: set MCP_TOKEN in the server settings; then clients must send  Authorization: Bearer <token>.
"""
import json
import os

from . import agent, daily, diagnosis, knowhow, machines, packs

PROTOCOL = "2025-06-18"
IND = {"type": "string", "description": "Industry pack id, e.g. factory, restaurant, healthcare, garage, it"}

TOOLS = [
    {"name": "ask_ustaad", "description": "Ask the team's memory about a problem. Returns the fix that worked before, who did it, "
                                          "what not to repeat, cause chances and trust level.",
     "inputSchema": {"type": "object", "required": ["industry", "question"], "properties": {
         "industry": IND, "question": {"type": "string"}, "machine_id": {"type": "string", "description": "optional, e.g. CNC-3"},
         "language": {"type": "string", "description": "en, hi, kn, ta, te, mr, bn, gu, ml, pa, od, hinglish"}}}},
    {"name": "search_memory", "description": "The team's own past cases for a problem — who did what, when, on which machine, and whether "
                                            "it WORKED or DID NOT WORK — with no AI rewriting. Use this when you want to write the answer "
                                            "yourself. Also returns what worked in other plants (names hidden).",
     "inputSchema": {"type": "object", "required": ["industry", "problem"], "properties": {
         "industry": IND, "problem": {"type": "string", "description": "the problem in any language"},
         "machine_id": {"type": "string", "description": "optional, e.g. CNC-3"}}}},
    {"name": "list_machines", "description": "All machines/assets in an industry with health and site.",
     "inputSchema": {"type": "object", "required": ["industry"], "properties": {"industry": IND}}},
    {"name": "machine_summary", "description": "Everything about one machine as Markdown: specs, expert report, service due, "
                                               "spare parts, fixes that worked, what didn't work, experts.",
     "inputSchema": {"type": "object", "required": ["industry", "machine_id"], "properties": {"industry": IND, "machine_id": {"type": "string"}}}},
    {"name": "cause_chances", "description": "Probability of each cause for a problem on a machine, from the team's own past cases, "
                                             "plus the smartest order to check (chance per minute).",
     "inputSchema": {"type": "object", "required": ["industry", "machine_id", "problem"], "properties": {
         "industry": IND, "machine_id": {"type": "string"}, "problem": {"type": "string"}}}},
    {"name": "find_expert", "description": "Who can fix something, ranked by proof (fixes that worked), e.g. 'hydraulic leak at Pune'.",
     "inputSchema": {"type": "object", "required": ["industry", "query"], "properties": {"industry": IND, "query": {"type": "string"}}}},
    {"name": "morning_briefing", "description": "Today's briefing: service due, parts out of stock, yesterday's problems, what may come back.",
     "inputSchema": {"type": "object", "required": ["industry"], "properties": {"industry": IND, "language": {"type": "string"}}}},
]


def _ind(x):
    if x not in packs.ids():
        raise ValueError(f"Unknown industry '{x}'. Use one of: {', '.join(packs.ids())}")
    return x


def call_tool(name, args):
    a = args or {}
    if name == "ask_ustaad":
        r = agent.ask(_ind(a.get("industry")), a.get("machine_id") or "ANY", a.get("question"), True, a.get("language") or "en")
        if r.get("mode") == "chart":
            return {"chart": r["chart"]}
        ans = r["answer"]
        return {"trust": r["trust"]["label"], "do_first": ans.get("check_first"), "summary": ans.get("summary"),
                "steps": ans.get("steps"), "dont_repeat": ans.get("avoid"), "safety": ans.get("safety"),
                "cause_chances": [{"cause": c["label"], "chance": c["p"]} for c in (r.get("diagnosis") or {}).get("causes", [])],
                "memories_used": [{"date": m.get("date"), "who": m.get("person"), "machine": m.get("asset_id"), "what": m.get("action"),
                                   "outcome": m.get("outcome")} for m in r["memories"] if m.get("used")],
                "other_plants": r.get("other_plants"), "written_by": r["written_by"]}
    if name == "search_memory":
        r = agent.search_memories(_ind(a.get("industry")), a.get("machine_id") or "ANY", a.get("problem"))
        keep = ("date", "person", "asset_id", "site", "problem", "cause", "action", "outcome", "downtime_minutes")
        return {"problem_read_as": r["problem_en"], "machine": r["asset"],
                "memories": [{**{k: m.get(k) for k in keep if m.get(k) not in (None, "")}, "trust": m["trust"]["label"],
                              "kind": m["kind"]} for m in r["memories"]],
                "other_plants": r["other_plants"],
                "how_to_read": "outcome 'fixed' = it worked; 'failed_again' = it did NOT work (don't repeat it); "
                               "'temporary' = it came back. Prefer fixes that worked, newest first."}
    if name == "list_machines":
        return {"machines": machines.summary_list(_ind(a.get("industry")))}
    if name == "machine_summary":
        return daily.machine_markdown(_ind(a.get("industry")), a.get("machine_id"))
    if name == "cause_chances":
        ind = _ind(a.get("industry"))
        asset = packs.asset(ind, a.get("machine_id"))
        if not asset:
            raise ValueError("Unknown machine")
        return diagnosis.causes(ind, asset, a.get("problem", "")) or {"cases": 0, "note": "No past cases of this problem yet."}
    if name == "find_expert":
        return knowhow.find_experts(_ind(a.get("industry")), a.get("query", ""))
    if name == "morning_briefing":
        b = daily.briefing(_ind(a.get("industry")), None, a.get("language") or "en")
        return {"text": b["text"], "items": b["items"]}
    raise ValueError(f"Unknown tool '{name}'")


def authorized(headers):
    token = os.getenv("MCP_TOKEN", "").strip()
    return not token or headers.get("Authorization", "") == f"Bearer {token}"


def handle(msg):
    """One JSON-RPC message -> a response dict, or None for notifications."""
    if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0":
        return {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid request"}}
    mid, method, params = msg.get("id"), msg.get("method"), msg.get("params") or {}
    if mid is None:  # a notification (e.g. notifications/initialized): nothing to answer
        return None
    try:
        if method == "initialize":
            return {"jsonrpc": "2.0", "id": mid, "result": {
                "protocolVersion": params.get("protocolVersion") or PROTOCOL, "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "ustaad", "title": "Ustaad — expert memory", "version": "1.0.0"},
                "instructions": "Ask the team's memory with ask_ustaad. Industries: " + ", ".join(packs.ids()) + "."}}
        if method == "ping":
            return {"jsonrpc": "2.0", "id": mid, "result": {}}
        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": mid, "result": {"tools": TOOLS}}
        if method == "tools/call":
            try:
                out = call_tool(params.get("name"), params.get("arguments"))
                text = out if isinstance(out, str) else json.dumps(out, ensure_ascii=False, default=str)
                return {"jsonrpc": "2.0", "id": mid, "result": {"content": [{"type": "text", "text": text}], "isError": False}}
            except Exception as e:  # a tool failing is a result the AI can read, not a protocol error
                return {"jsonrpc": "2.0", "id": mid, "result": {"content": [{"type": "text", "text": f"Error: {e}"}], "isError": True}}
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"Method not found: {method}"}}
    except Exception as e:
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32603, "message": str(e)[:200]}}
