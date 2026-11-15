"""
Expert fill — reads a source bundle the way an experienced engineer would.

  1. identify  which maker, which model family, which exact model (a range page -> the person picks theirs)
  2. extract   the fields that matter for THIS kind of machine (spec templates), each with value, unit and the
               exact words + place it came from
  3. verify    in code, not by the AI: the value must really appear in the source, units are converted to one
               standard (hp -> kW, psi -> bar, cfm -> l/min ...), impossible values are flagged

Every field ends up green (found and checked), amber (worked out / converted / not found word-for-word) or
red (missing or impossible). Without an AI key, fields are still filled from exact table rows.
"""
import re

from . import llm, packs, reader

# ---------- spec templates: (key, label, unit, min, max) — unit "" means text ----------
T = {
    "cnc": ("CNC machining centre", ["cnc", "machining cent", "vmc", "hmc", "milling", "mill"], [
        ("spindle_speed", "Max spindle speed", "rpm", 100, 60000), ("spindle_power", "Spindle motor power", "kW", 0.5, 200),
        ("x_travel", "X-axis travel", "mm", 50, 10000), ("y_travel", "Y-axis travel", "mm", 50, 6000),
        ("z_travel", "Z-axis travel", "mm", 50, 3000), ("table_size", "Table size", "", None, None),
        ("table_load", "Max table load", "kg", 10, 60000), ("tools", "Tool magazine capacity", "tools", 1, 400),
        ("rapid", "Rapid traverse", "m/min", 1, 200), ("controller", "CNC controller", "", None, None),
        ("voltage", "Supply voltage", "V", 100, 1000), ("frequency", "Supply frequency", "Hz", 40, 70),
        ("power_capacity", "Power capacity", "kVA", 1, 500), ("air_pressure", "Air supply pressure", "bar", 1, 15),
        ("air_consumption", "Air consumption", "l/min", 1, 5000), ("weight", "Machine weight", "kg", 100, 200000)]),
    "lathe": ("Lathe / turning centre", ["lathe", "turning"], [
        ("spindle_speed", "Max spindle speed", "rpm", 50, 12000), ("spindle_power", "Spindle motor power", "kW", 0.5, 200),
        ("chuck", "Chuck size", "mm", 50, 2000), ("swing", "Swing over bed", "mm", 100, 5000),
        ("between_centres", "Distance between centres", "mm", 100, 20000), ("controller", "CNC controller", "", None, None),
        ("voltage", "Supply voltage", "V", 100, 1000), ("weight", "Machine weight", "kg", 100, 200000)]),
    "compressor": ("Air compressor", ["compressor", "kompressor", "air end", "screw", "reciprocating"], [
        ("fad", "Free air delivery (flow)", "l/min", 10, 200000), ("pressure", "Working pressure", "bar", 1, 60),
        ("motor_power", "Motor power", "kW", 0.1, 1500), ("receiver", "Air receiver (tank)", "L", 1, 20000),
        ("noise", "Noise level", "dB(A)", 30, 130), ("voltage", "Supply voltage", "V", 100, 1000),
        ("frequency", "Supply frequency", "Hz", 40, 70), ("cooling", "Cooling", "", None, None),
        ("oil", "Recommended oil", "", None, None), ("weight", "Weight", "kg", 5, 50000)]),
    "press": ("Hydraulic press", ["press", "hydraulic"], [
        ("tonnage", "Capacity", "t", 1, 10000), ("stroke", "Stroke", "mm", 10, 3000), ("daylight", "Daylight", "mm", 50, 5000),
        ("bed", "Bed size", "", None, None), ("motor_power", "Motor power", "kW", 0.5, 500),
        ("pressure", "Max hydraulic pressure", "bar", 10, 1000), ("speed", "Ram speed", "mm/s", 1, 1000),
        ("oil", "Hydraulic oil", "", None, None), ("weight", "Weight", "kg", 100, 500000)]),
    "boiler": ("Boiler", ["boiler", "steam"], [
        ("steam", "Steam output", "kg/h", 10, 200000), ("pressure", "Working pressure", "bar", 0.5, 250),
        ("fuel", "Fuel", "", None, None), ("efficiency", "Efficiency", "%", 40, 100),
        ("water", "Water capacity", "L", 10, 200000), ("weight", "Weight", "kg", 50, 500000)]),
    "generator": ("Generator / DG set", ["generator", "genset", "dg set", "diesel generator"], [
        ("rating", "Rating", "kVA", 1, 10000), ("voltage", "Voltage", "V", 100, 15000), ("frequency", "Frequency", "Hz", 40, 70),
        ("fuel_use", "Fuel consumption", "l/h", 0.1, 3000), ("engine", "Engine", "", None, None),
        ("tank", "Fuel tank", "L", 5, 50000), ("noise", "Noise level", "dB(A)", 30, 130)]),
    "pump": ("Pump", ["pump"], [
        ("flow", "Flow", "m3/h", 0.01, 50000), ("head", "Head", "m", 0.5, 3000), ("motor_power", "Motor power", "kW", 0.05, 5000),
        ("speed", "Speed", "rpm", 100, 10000), ("ports", "Inlet / outlet size", "", None, None), ("voltage", "Voltage", "V", 100, 15000)]),
    "fryer": ("Fryer", ["fryer", "fritteuse", "deep fry"], [
        ("oil_capacity", "Oil capacity", "L", 1, 200), ("heat_input", "Heat input", "kW", 1, 150),
        ("fuel", "Fuel / power type", "", None, None), ("burners", "Burners / heating elements", "count", 1, 20),
        ("temperature", "Temperature range", "°C", 50, 260), ("gas_pressure", "Gas pressure", "", None, None),
        ("baskets", "Baskets", "count", 1, 10), ("dimensions", "Size (W × D × H)", "", None, None)]),
    "cold": ("Refrigeration / cold room", ["cold", "refrigerat", "freezer", "chiller", "cold room"], [
        ("capacity", "Capacity", "L", 10, 500000), ("temperature", "Temperature range", "°C", -60, 20),
        ("refrigerant", "Refrigerant", "", None, None), ("compressor_power", "Compressor power", "kW", 0.05, 500),
        ("voltage", "Voltage", "V", 100, 1000)]),
    "oven": ("Oven / tandoor / range", ["oven", "tandoor", "range", "tawa", "griddle", "charbroiler", "cooker"], [
        ("max_temp", "Max temperature", "°C", 80, 600), ("heat_input", "Heat input", "kW", 0.5, 200),
        ("fuel", "Fuel / power type", "", None, None), ("capacity", "Capacity", "", None, None),
        ("dimensions", "Size (W × D × H)", "", None, None)]),
    "ventilator": ("Ventilator", ["ventilator"], [
        ("modes", "Ventilation modes", "", None, None), ("tidal_volume", "Tidal volume range", "mL", 1, 4000),
        ("rate", "Respiratory rate range", "bpm", 1, 150), ("peep", "PEEP range", "cmH2O", 0, 50),
        ("fio2", "FiO2 range", "%", 21, 100), ("battery", "Battery runtime", "min", 5, 1440),
        ("weight", "Weight", "kg", 1, 200)]),
    "infusion-pump": ("Infusion pump", ["infusion", "syringe pump"], [
        ("flow_range", "Flow rate range", "mL/h", 0.01, 3000), ("accuracy", "Accuracy", "%", 0.1, 20),
        ("battery", "Battery runtime", "h", 0.5, 100), ("occlusion", "Occlusion pressure", "", None, None),
        ("syringes", "Syringe sizes", "", None, None)]),
    "autoclave": ("Steriliser / autoclave", ["autoclave", "sterili"], [
        ("chamber", "Chamber volume", "L", 1, 10000), ("max_temp", "Max temperature", "°C", 100, 150),
        ("pressure", "Max pressure", "bar", 0.5, 6), ("cycle", "Cycle time", "min", 3, 300),
        ("power", "Power", "kW", 0.5, 200), ("voltage", "Voltage", "V", 100, 1000)]),
    "vehicle": ("Vehicle", ["car", "vehicle", "suv", "sedan", "hatchback", "two-wheeler", "scooter", "motorcycle", "ev"], [
        ("engine", "Engine displacement", "cc", 50, 10000), ("power", "Power", "kW", 1, 1500), ("torque", "Torque", "Nm", 1, 3000),
        ("fuel", "Fuel", "", None, None), ("transmission", "Transmission", "", None, None),
        ("battery", "Battery capacity", "kWh", 0.5, 300), ("range", "Range", "km", 10, 2000)]),
    "software": ("Server / software", ["server", "database", "cluster", "dns", "service", "software", "certificate"], [
        ("version", "Version", "", None, None), ("cpu", "vCPU / cores", "count", 1, 1024), ("ram", "Memory", "GB", 0.1, 100000),
        ("storage", "Storage", "", None, None), ("os", "Operating system", "", None, None), ("ports", "Ports", "", None, None)]),
    "general": ("Equipment", [], [
        ("power", "Rated power", "kW", 0.01, 100000), ("voltage", "Voltage", "V", 1, 50000), ("capacity", "Capacity", "", None, None),
        ("dimensions", "Size (W × D × H)", "", None, None), ("weight", "Weight", "kg", 0.1, 1000000)]),
}
PACK_TYPE = {"cnc": "cnc", "press": "press", "compressor": "compressor", "boiler": "boiler", "fryer": "fryer", "cold": "cold",
             "tandoor": "oven", "tawa": "oven", "ventilator": "ventilator", "infusion-pump": "infusion-pump",
             "autoclave": "autoclave", "civic": "vehicle", "corolla": "vehicle", "diesel": "vehicle", "ev": "vehicle",
             "petrol": "vehicle", "database": "software", "config": "software", "general": "software", "time": "software"}

# label words that map exact table rows to fields without any AI
ALIASES = {
    "spindle_speed": ["spindle speed", "max spindle", "spindle rpm", "max. spindle"], "spindle_power": ["spindle power", "spindle motor", "main motor"],
    "x_travel": ["x axis", "x-axis", "x travel", "longitudinal"], "y_travel": ["y axis", "y-axis", "y travel", "cross travel"],
    "z_travel": ["z axis", "z-axis", "z travel", "vertical travel"], "table_size": ["table size", "table dimension", "working surface"],
    "table_load": ["table load", "max load", "load capacity"], "tools": ["tool capacity", "magazine", "atc", "number of tools"],
    "rapid": ["rapid", "rapids"], "controller": ["control", "controller", "cnc system"], "voltage": ["supply voltage", "voltage"],
    "frequency": ["frequency"], "power_capacity": ["capacity", "kva", "power capacity"], "air_pressure": ["air pressure", "pneumatic pressure", "pressure"],
    "air_consumption": ["air consumption"], "weight": ["weight", "net weight", "machine weight", "gewicht"],
    "fad": ["free air delivery", "fad", "air delivery", "capacity", "displacement", "flow", "liefermenge"],
    "pressure": ["working pressure", "max pressure", "pressure", "operating pressure", "druck"],
    "motor_power": ["motor power", "drive motor", "main motor", "rated power", "motor", "nominal power"],
    "receiver": ["receiver", "tank", "air receiver", "behälter"], "noise": ["noise", "sound", "db(a)", "schall"],
    "cooling": ["cooling"], "oil": ["oil", "lubricant"], "tonnage": ["capacity", "tonnage", "press force"], "stroke": ["stroke"],
    "daylight": ["daylight", "open height"], "oil_capacity": ["oil capacity", "fry pot", "frypot", "oil volume"],
    "heat_input": ["btu", "heat input", "power", "kw"], "fuel": ["gas type", "fuel", "gas"], "burners": ["burners", "# of burners"],
    "temperature": ["temperature"], "dimensions": ["dimensions", "w x d x h", "size"], "baskets": ["basket"],
}

# unit conversion to the template's unit: (from_unit_pattern, to_unit, factor or function)
CONV = [
    (r"^(hp|bhp|ps)$", "kW", 0.7457), (r"^w$", "kW", 0.001), (r"^(btu|btu/h|btu/hr|btuh)$", "kW", 0.000293071),
    (r"^(kcal/h)$", "kW", 0.001163), (r"^(in|inch|inches|\")$", "mm", 25.4), (r"^cm$", "mm", 10), (r"^m$", "mm", 1000),
    (r"^(lb|lbs)$", "kg", 0.45359), (r"^(t|ton|tonne|tonnes)$", "kg", 1000), (r"^psi(g)?$", "bar", 0.0689476),
    (r"^mpa$", "bar", 10), (r"^kpa$", "bar", 0.01), (r"^(kgf/cm2|kg/cm2|kgf/cm²|kg/cm²|at)$", "bar", 0.980665),
    (r"^(bar ?g|barg|bar\(g\)|bar \(g\))$", "bar", 1), (r"^(cfm|ft3/min)$", "l/min", 28.3168), (r"^(m3/min|m³/min)$", "l/min", 1000),
    (r"^(m3/h|m³/h)$", "l/min", 16.6667), (r"^(l/s)$", "l/min", 60), (r"^(nl/min)$", "l/min", 1),
    (r"^(gal|gallon|gallons|us gal)$", "L", 3.78541), (r"^(ml)$", "L", 0.001), (r"^(in/min|ipm)$", "m/min", 0.0254),
    (r"^(mm/min)$", "m/min", 0.001), (r"^(ft/min)$", "m/min", 0.3048), (r"^(l/min)$", "m3/h", 0.06),
    (r"^(gpm)$", "m3/h", 0.227125), (r"^(kn)$", "t", 0.10197), (r"^(°f|f|deg f)$", "°C", "F"),
]


def _norm(s):
    return re.sub(r"[^a-z0-9.]+", " ", (s or "").lower().replace(",", "")).strip()


def _numbers(s):
    return [float(x.replace(",", "")) for x in re.findall(r"-?\d[\d,]*\.?\d*", str(s or "")) if re.search(r"\d", x)]


def convert(value_num, unit, target):
    u = (unit or "").strip().lower().replace(" ", "") if unit else ""
    if not target or not u or u == target.lower().replace(" ", ""):
        return value_num, False
    for pat, to, f in CONV:
        if to.lower() == target.lower() and re.match(pat, u):
            if f == "F":
                return round((value_num - 32) * 5 / 9, 1), True
            return round(value_num * f, 3 if value_num * f < 10 else 1), True
    if target == "kg" and u in ("t", "ton", "tonne"):
        return value_num * 1000, True
    return value_num, False


WORDS = {"cnc": ["cnc", "machining cent*", "machining center*", "vmc", "hmc", "milling machine*", "vertical mill*"],
         "lathe": ["lathe*", "turning cent*", "turning center*"],
         "compressor": ["compressor*", "kompressor*", "air end", "airend", "free air delivery"],
         "press": ["hydraulic press*", "press brake*", "power press*", "presses", "tonnage"],
         "boiler": ["boiler*", "steam generator*"], "generator": ["generator*", "genset*", "dg set*", "alternator*"],
         "pump": ["pump", "pumps", "centrifugal pump*", "submersible"], "fryer": ["fryer*", "fritteuse", "deep fry*", "frypot*", "fry pot*"],
         "cold": ["refrigerat*", "freezer*", "chiller*", "cold room*", "cold storage"],
         "oven": ["oven*", "tandoor*", "griddle*", "charbroiler*", "combi steamer*"], "ventilator": ["ventilator*"],
         "infusion-pump": ["infusion pump*", "syringe pump*"], "autoclave": ["autoclave*", "sterilizer*", "steriliser*"],
         "vehicle": ["car", "cars", "vehicle*", "suv", "sedan", "hatchback", "two-wheeler*", "scooter*", "motorcycle*"],
         "software": ["server*", "database*", "kubernetes", "cluster*", "dns", "software", "certificate*"]}


def guess_type(text, pack_type=None, title=""):
    if pack_type and PACK_TYPE.get(pack_type):
        return PACK_TYPE[pack_type]
    body, head = (text or "").lower(), (title or "").lower()
    best, hits = "general", 0
    for key, words in WORDS.items():
        n = 0
        for w in words:
            pat = r"\b" + re.escape(w.rstrip("*")) + ("" if w.endswith("*") else r"\b")
            n += len(re.findall(pat, body)) + 5 * len(re.findall(pat, head))
        if n > hits:
            best, hits = key, n
    return best


def template(key):
    label, _, fields = T.get(key) or T["general"]
    return {"key": key if key in T else "general", "label": label,
            "fields": [{"key": k, "label": lb, "unit": u, "min": lo, "max": hi} for k, lb, u, lo, hi in fields]}


# ---------- 1 · identify ----------
MODEL_CODE = re.compile(r"^(?=.*\d)(?=.*[A-Za-z])[A-Za-z0-9][A-Za-z0-9 ./-]{2,24}$")


def table_models(b):
    """Model numbers that head the rows of a model table (e.g. 351FCPG15N … 351FCPG30L)."""
    out = []
    for r in b["rows"]:
        if r["where"].endswith("table") and "; " in r["value"] and ": " in r["value"] and MODEL_CODE.match(r["label"]):
            if r["label"] not in out:
                out.append(r["label"])
    return out[:12] if len(out) >= 2 else []


def identify(industry, b):
    pk = packs.get(industry)
    text = reader.context(b, budget=3500, rows_budget=1500)
    prod = b.get("product") or {}
    guess = {"maker": prod.get("brand") or "", "model_family": prod.get("name") or b.get("title") or "",
             "models": [m for m in [prod.get("model"), prod.get("mpn")] if m] + table_models(b),
             "exact_model": prod.get("model") or "",
             "type": guess_type(reader.all_text(b)[:40000], title=(b.get("title") or "") + " " + (prod.get("name") or "")),
             "summary": ""}
    if not llm.available():
        return guess
    keys = ", ".join(f"{k} ({v[0]})" for k, v in T.items())
    data = llm.chat_json(
        f"You are a senior {pk['labels']['person'].lower()} identifying a {pk['labels']['asset'].lower()} from its maker's "
        "page, datasheet or manual (any language). Use only what the text says.",
        f"{text}\n\nReturn ONLY JSON: {{\"maker\": \"\", \"model_family\": \"series or family name\", "
        f"\"models\": [\"every distinct model number the text lists, exactly as written, max 12\"], "
        f"\"exact_model\": \"the single model if the text is about one model, else empty\", "
        f"\"type\": \"one of: {keys}\", \"summary\": \"one plain English sentence: what it is and what it's for\"}}",
        max_tokens=700)
    if isinstance(data, dict):
        out = {**guess, **{k: v for k, v in data.items() if v}}
        found = [str(m)[:40] for m in (out.get("models") or []) if m]
        out["models"] = (found + [m for m in guess["models"] if m not in found])[:12]
        if out.get("type") not in T:
            out["type"] = guess["type"]
        return out
    return guess


# ---------- 2 · extract ----------
def extract(industry, b, ident, model=None):
    tpl = template(ident.get("type"))
    pk = packs.get(industry)
    target = model or ident.get("exact_model") or ""
    fields_txt = "\n".join(f"- {f['key']}: {f['label']}" + (f" (unit {f['unit']})" if f["unit"] else "") for f in tpl["fields"])
    data = None
    if llm.available():
        data = llm.chat_json(
            f"You are a meticulous senior {pk['labels']['person'].lower()} filling a {tpl['label'].lower()} register from the "
            "maker's documents (any language — answer in English, but copy quotes exactly as written). RULES: use ONLY facts in "
            "the text; never invent numbers, codes or part numbers; if a field isn't stated, leave its value empty. For each "
            "value give the unit exactly as the source writes it, an exact short quote (max 12 words) copied from the source "
            "that contains the value, and where it is (e.g. 'page 45', 'web page table'). Prefer EXACT TABLE ROWS. "
            + (f"The person's machine is model {target}: when the source lists several models, give that model's values "
               "only. " if target else "If the source covers a range of models, give the range (e.g. '112–1050'). "),
            f"Fields to fill:\n{fields_txt}\n\nSOURCE:\n{reader.context(b)}\n\n"
            "Return ONLY JSON: {\"fields\": {\"<field key>\": {\"value\": \"\", \"unit\": \"\", \"quote\": \"\", \"where\": \"\"}}, "
            "\"extra_specs\": [{\"label\": \"\", \"value\": \"\", \"quote\": \"\", \"where\": \"\"}], "
            "\"components\": [{\"name\": \"part that wears or gets replaced\", \"part_no\": \"\", \"every_days\": null}], "
            "\"faults\": [{\"title\": \"\", \"code\": \"alarm/error code or empty\", \"symptoms\": \"\", \"cause\": \"\", \"fix\": \"\"}], "
            "\"service\": [{\"task\": \"\", \"every_days\": 1}], \"warranty_months\": null}. Max 6 extra_specs, 10 components, "
            "8 faults (include alarm codes from alarm lists), 8 service tasks (daily 1, weekly 7, monthly 30, half-yearly 180, "
            "yearly 365).", max_tokens=3000)
    if not isinstance(data, dict):
        data = {"fields": {}, "note": "Filled from exact table rows only (no AI key)."}
    raw = data.get("fields") if isinstance(data.get("fields"), dict) else {}
    # no-AI help: fill empty fields straight from exact table rows whose label matches
    pairs = []  # (label, value, where) — a model's row in a model table is split into its columns
    for r in b["rows"]:
        if target and _norm(target) and _norm(target) in _norm(r["label"]) and ": " in r["value"]:
            for part in r["value"].split("; "):
                if ": " in part:
                    h, v = part.split(": ", 1)
                    pairs.append((h, v, r["where"], f"{r['label']} — {h}: {v}"))
        elif "part no." not in r["value"]:
            pairs.append((r["label"], r["value"], r["where"], f"{r['label']}: {r['value']}"))
    for f in tpl["fields"]:
        cur = raw.get(f["key"]) if isinstance(raw.get(f["key"]), dict) else {}
        if cur.get("value"):
            continue
        for lab, val, where, quote in pairs:
            low = lab.lower()
            if not (any(a in low for a in ALIASES.get(f["key"], [])) or f["label"].lower() in low):
                continue
            if f["unit"] and not re.search(r"\d", val):
                continue  # a number field needs a number
            if len(val) > 90:
                continue
            unit = "" if _unit_in(val) else (_unit_in(lab) or "")
            raw[f["key"]] = {"value": val, "unit": unit, "quote": quote[:120], "where": where, "from_table": True}
            break
    data["fields"] = raw
    data["model"] = target
    if not data.get("warranty_months"):
        data["warranty_months"] = warranty_months(reader.all_text(b))
    return tpl, data


NUMWORD = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "twelve": 12, "eighteen": 18, "twenty-four": 24}


def warranty_months(text):
    """'1 year limited warranty', 'warranted for twelve (12) months', 'Garantie 2 Jahre' -> months (no AI needed)."""
    t = re.sub(r"\s+", " ", (text or "").lower())
    pats = [r"warrant(?:s|y|ed)?[^.]{0,110}?(?:period of|for)\s*(\d{1,2}|one|two|three|five|twelve|eighteen|twenty-four)\s*(?:\(\d+\)\s*)?[- ]?(year|yr|month)s?",
            r"(\d{1,2}|one|two|three|five|twelve|eighteen|twenty-four)\s*(?:\(\d+\)\s*)?[- ]?(year|yr|month)s?[^.\n]{0,30}?(?:limited\s+)?(?:warranty|guarantee|garantie)",
            r"(?:warranty|warranted|guarantee|garantie)[^.\n]{0,60}?(\d{1,2}|one|two|three|five|twelve|eighteen|twenty-four)\s*(?:\(\d+\)\s*)?[- ]?(year|yr|month|jahr)s?"]
    for pat in pats:
        m = re.search(pat, t)
        if m:
            n = NUMWORD.get(m.group(1)) or (int(m.group(1)) if m.group(1).isdigit() else 0)
            months = n * 12 if m.group(2) in ("year", "yr", "jahr") else n
            if 1 <= months <= 120:
                return months
    return None


# ---------- 3 · verify (code, not AI) ----------
def _unit_in(text):
    m = re.search(r"(kgf/cm2|kg/cm2|kgf/cm²|m3/min|m³/min|m3/h|m³/h|l/min|nl/min|l/s|cfm|psig|psi|bar ?g|barg|bar|mpa|kpa|"
                  r"kw|kva|hp|bhp|btu(?:/h|/hr)?|kcal/h|rpm|mm|cm|inch|in|kg|lbs|lb|tonnes|tonne|tons|ton|t\b|db\(a\)|dba|db|"
                  r"hz|v\b|vac|vdc|l\b|litres|liters|gal|°c|°f|min\b|m/min|ipm|nm|cc|kwh|km|gb)", (text or "").lower())
    return m.group(1) if m else ""


def verify(b, tpl, data):
    hay = _norm(reader.all_text(b))
    fields, counts = [], {"verified": 0, "converted": 0, "unverified": 0, "suspicious": 0, "missing": 0}
    for f in tpl["fields"]:
        d = data["fields"].get(f["key"]) if isinstance(data["fields"].get(f["key"]), dict) else {}
        value = str(d.get("value") or "").strip()
        out = {**f, "value": value, "unit_given": str(d.get("unit") or "").strip(), "quote": str(d.get("quote") or "")[:160],
               "where": str(d.get("where") or "")[:80], "status": "missing", "std": None, "note": ""}
        if not value:
            counts["missing"] += 1
            fields.append(out)
            continue
        nums = _numbers(re.sub(r"\([^)]*\)", " ", value)) or _numbers(value)  # '500 nl/min (26.4 gpm)' is one value, not a range
        q = _norm(out["quote"])
        quote_found = bool(q) and q in hay
        nums_found = bool(nums) and all(_norm(str(int(n) if n == int(n) else n)) in hay for n in nums[:3])
        text_found = not nums and _norm(value)[:30] in hay
        found = quote_found or nums_found or text_found or bool(d.get("from_table"))
        status = "verified" if found else "unverified"
        if f["unit"] and nums:
            unit = out["unit_given"] or _unit_in(value) or _unit_in(out["quote"])
            vals = []
            converted = False
            for n in nums[:2]:
                v, c = convert(n, unit, f["unit"])
                vals.append(v)
                converted = converted or c
            out["std"] = vals[0] if len(vals) == 1 else vals
            if converted:
                out["note"] = f"converted from {unit} to {f['unit']}"
                if status == "verified":
                    status = "converted"
            lo, hi = f["min"], f["max"]
            if lo is not None and any(not (lo <= v <= hi) for v in vals):
                status = "suspicious"
                out["note"] = (out["note"] + "; " if out["note"] else "") + f"outside the normal range ({lo}–{hi} {f['unit']})"
        out["status"] = status
        counts[status] += 1
        fields.append(out)
    extra = []
    for e in (data.get("extra_specs") or [])[:6]:
        if isinstance(e, dict) and e.get("label") and e.get("value"):
            ok = _norm(str(e.get("quote") or ""))[:60] in hay or all(_norm(str(int(n) if n == int(n) else n)) in hay
                                                                       for n in _numbers(e["value"])[:2])
            extra.append({"label": str(e["label"])[:60], "value": str(e["value"])[:100], "quote": str(e.get("quote") or "")[:160],
                          "where": str(e.get("where") or "")[:80], "status": "verified" if ok else "unverified"})
    filled = len(tpl["fields"]) - counts["missing"]
    return {"fields": fields, "extra": extra, "counts": counts,
            "score": round(100 * (counts["verified"] + counts["converted"]) / filled) if filled else 0}


def show(field):
    """How a field is written on the machine page, e.g. '8000 rpm' or '22.4 kW (from 30 hp)'."""
    v = str(field.get("value") or "").strip()
    if not v:
        return ""
    ug = str(field.get("unit_given") or "").strip()
    base = v if (not ug or ug.lower() in v.lower()) else f"{v} {ug}"
    std = field.get("std")
    if std is not None and str(field.get("note", "")).startswith("converted"):
        s = "–".join(f"{x:g}" for x in std) if isinstance(std, list) else f"{std:g}"
        return f"{s} {field['unit']} (from {base})"
    return base
