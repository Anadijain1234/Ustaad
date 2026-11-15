"""Reader tests: web pages, PDF tables, parts lists, scanned pages, unit checks, the AI being caught out, and the
accuracy scorer. Offline: the AI and the internet are replaced by fakes.  Run:  python tests/test_reader.py"""
import base64
import io
import os
import sys
import tempfile
from pathlib import Path

for _k in ("HINDSIGHT_API_KEY", "GROQ_API_KEY", "SARVAM_API_KEY", "GITHUB_TOKEN", "GITHUB_REPO"):
    os.environ[_k] = ""
os.environ["DB_PATH"] = str(Path(tempfile.mkdtemp()) / "test.db")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import app as A  # noqa: E402,F401  (creates the database)
from ustaad import benchmark, llm, machines, reader, specs  # noqa: E402


def close(a, b, tol=0.02):
    return abs(a - b) <= tol * abs(b)


def test_units():
    assert close(specs.convert(64, "cfm", "l/min")[0], 1812)
    assert close(specs.convert(15, "hp", "kW")[0], 11.19)
    assert close(specs.convert(53000, "BTU", "kW")[0], 15.53)
    assert close(specs.convert(5, "kgf/cm2", "bar")[0], 4.90)
    assert close(specs.convert(100, "psi", "bar")[0], 6.89)
    assert specs.convert(380, "V", "V") == (380, False)


def test_machine_type_whole_words():
    assert specs.guess_type("Read carefully before use. Compressor pressure 10 bar.") == "compressor"  # not 'car', not 'press'
    assert specs.guess_type("Operation manual", title="VMC 1050 vertical machining centre") == "cnc"
    assert specs.guess_type("Gas fryer, frypot, 4 burners") == "fryer"
    assert specs.guess_type("pump", pack_type="garage-car") in specs.T


def test_ssrf_guard():
    for bad in ("http://127.0.0.1/x", "http://localhost:5000/", "http://169.254.169.254/latest/meta-data", "file:///etc/passwd"):
        try:
            reader.check_url(bad)
        except ValueError:
            continue
        raise AssertionError(f"should block {bad}")


HTML = b"""<html><head><title>AirMax 50 screw compressor</title>
<script type="application/ld+json">{"@type": "Product", "name": "AirMax 50", "brand": {"name": "Acme Air"}, "model": "AM-50"}</script>
</head><body><h1>AirMax 50</h1><table><tr><td>Free air delivery</td><td>64 cfm</td></tr><tr><td>Motor power</td><td>15 hp</td></tr>
<tr><td>Working pressure</td><td>100 psi</td></tr></table><p>Rated voltage 415 V</p></body></html>"""


def test_web_page_tables_and_product_data():
    real = reader._get, reader.check_url
    reader._get = lambda url, timeout=20: (url, "text/html", HTML)
    reader.check_url = lambda url: url  # offline: no DNS lookup
    try:
        d = machines.read_source("factory", url="https://example.com/airmax-50")
    finally:
        reader._get, reader.check_url = real
    f = {x["key"]: x for x in d["spec_fields"]}
    assert d["template"] == "compressor" and d["maker"] == "Acme Air"
    assert close(f["fad"]["std"], 1812, 0.01) and f["fad"]["status"] == "converted"
    assert close(f["motor_power"]["std"], 11.19) and close(f["pressure"]["std"], 6.89)
    assert "web page" in f["fad"]["where"]


def _pdf(draw):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    draw(c)
    c.save()
    return buf.getvalue()


def _table(c, x, y, rows, widths):
    h = 18
    for i, row in enumerate(rows):
        cx = x
        for w, cell in zip(widths, row):
            c.rect(cx, y - (i + 1) * h, w, h)
            c.drawString(cx + 3, y - (i + 1) * h + 5, cell)
            cx += w


def test_pdf_model_table_parts_list_and_model_picker():
    try:
        import reportlab  # noqa: F401
    except ImportError:
        print("  (skipped: reportlab not installed)")
        return

    def draw(c):
        c.setFont("Helvetica", 9)
        c.drawString(40, 800, "CPG Gas Fryer - Specifications")
        _table(c, 40, 780, [["ITEM #", "# OF BURNERS", "POWER", "WORK PRESSURE"], ["FX15N", "2", "26,500 BTU", "4"],
                            ["FX30N", "4", "53,000 BTU", "4"]], [90, 90, 90, 110])
        c.drawString(40, 690, "This fryer carries a 1 year limited warranty.")
        c.showPage()
        c.setFont("Helvetica", 9)
        c.drawString(40, 800, "Parts list")
        _table(c, 40, 780, [["#", "DESCRIPTION", "CODE", "QTY"], ["1", "BASKET", "01.02.1005190", "2"],
                            ["2", "THERMOSTAT", "01.22.1069501", "1"]], [30, 120, 110, 40])
        c.showPage()
    data = _pdf(draw)
    d = machines.read_source("restaurant", file=(data, "fryer.pdf", "application/pdf"))
    assert d["template"] == "fryer" and {"FX15N", "FX30N"} <= set(d["models"]), d["models"]
    assert {p["part_no"] for p in d["parts_found"]} >= {"01.02.1005190", "01.22.1069501"}
    assert d["warranty_months"] == 12
    d2 = machines.read_source("restaurant", read_id=d["read_id"], model="FX30N")  # the model picker: no re-reading
    f = {x["key"]: x for x in d2["spec_fields"]}
    assert close(f["heat_input"]["std"], 15.53) and f["burners"]["value"] == "4", f["heat_input"]
    assert "page 1" in f["heat_input"]["where"]


def test_scanned_pdf_goes_to_vision_and_ai_is_checked():
    """An image-only PDF is read by the vision AI; then a value the AI invented is caught (🟠) and a silly one flagged (🔴)."""
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (900, 600), "white")
    ImageDraw.Draw(img).text((40, 40), "NAMEPLATE  SPINDLE 8000 RPM  380 V 50 HZ", fill="black")
    buf = io.BytesIO()
    img.save(buf, format="PDF")
    calls = {"vision": 0, "chat": 0}

    def fake_vision(prompt, image_b64, mime="image/jpeg", max_tokens=900):
        calls["vision"] += 1
        assert base64.b64decode(image_b64)[:2] == b"\xff\xd8"  # a real JPEG of the page was sent
        return {"kind": "nameplate", "rows": [{"label": "Spindle speed", "value": "8000 rpm"}, {"label": "Supply voltage", "value": "380 V"}],
                "text": "VMC-850 machining centre. Spindle 8000 rpm. Supply 380 V 50 Hz."}

    def fake_chat(system, user, max_tokens=1800):
        calls["chat"] += 1
        if '"models"' in user:  # pass 1: identify
            return {"maker": "Acme", "model_family": "VMC-850", "models": ["VMC-850"], "exact_model": "VMC-850", "type": "cnc", "summary": "A machining centre."}
        return {"fields": {"spindle_speed": {"value": "8000", "unit": "rpm", "quote": "Spindle speed: 8000 rpm", "where": "page 1"},
                           "voltage": {"value": "380", "unit": "V", "quote": "380 V", "where": "page 1"},
                           "tools": {"value": "24", "unit": "", "quote": "24 tool ATC", "where": "page 1"},          # invented
                           "spindle_power": {"value": "9000", "unit": "kW", "quote": "", "where": ""}},             # silly
                "extra_specs": [], "components": [], "faults": [], "service": [], "warranty_months": None}
    saved = (llm.available, llm.groq_available, llm.vision_json, llm.chat_json)
    llm.available = llm.groq_available = lambda: True
    llm.vision_json, llm.chat_json = fake_vision, fake_chat
    try:
        d = machines.read_source("factory", file=(buf.getvalue(), "scan.pdf", "application/pdf"))
    finally:
        llm.available, llm.groq_available, llm.vision_json, llm.chat_json = saved
    f = {x["key"]: x for x in d["spec_fields"]}
    assert calls["vision"] == 1 and calls["chat"] == 2
    assert f["spindle_speed"]["status"] == "verified" and f["voltage"]["status"] == "verified"
    assert f["tools"]["status"] == "unverified", f["tools"]
    assert f["spindle_power"]["status"] == "suspicious", f["spindle_power"]
    assert d["read"]["sources"][0].get("vision_pages") == [1]


def test_text_lines_without_tables():
    b = reader.read_text("Machine data\nSupply Voltage 380 VAC\nCapacity 22 KVA\nwww.example.com 3\nArial 6.5pt\nmore text here")
    reader._line_rows(b, b["pages"][0], "test")
    labels = [r["label"] for r in b["rows"]]
    assert "Supply Voltage" in labels and "Capacity" in labels
    assert not any("www" in x.lower() or x.lower().startswith("arial") for x in labels)


def test_save_keeps_pages_ask_manual_and_calendar():
    d = machines.read_source("factory", text="Model VX-1 vertical machining centre\nSupply voltage: 415 V\n"
                                             "Way lube: fill with ISO VG 68 oil every 7 days. Low lube alarm 2071 means the tank is empty.")
    machines.save("factory", {**d, "id": "VX-1", "is_new": True, "name": "VX-1 VMC", "site": "blr",
                              "install_date": "2026-01-10", "components": [{"name": "Way lube filter", "every_days": 30}]}, "imran", "supervisor")
    r = machines.ask_manual("factory", "VX-1", "what oil for alarm 2071?")
    assert r["pages"] and "VG 68" in r["answer"]
    ics = machines.service_ics("factory", "VX-1")
    assert ics.startswith("BEGIN:VCALENDAR") and "Way lube filter" in ics and "RRULE:FREQ=DAILY;INTERVAL=30" in ics
    prof = machines.profile("factory", "VX-1")
    assert prof["manual_pages"] >= 1 and any(f["key"] == "voltage" and f["value"] for f in prof["spec_fields"])


def test_benchmark_scoring():
    case = {"expect": [{"type": "fryer"}, {"key": "heat_input", "approx": 15.53, "tol": 0.03}, {"part": "01.02.1005190"},
                       {"key": "burners", "approx": 4, "tol": 0.01}]}
    draft = {"template": "fryer", "spec_fields": [{"key": "heat_input", "label": "Heat input", "unit": "kW", "value": "53,000 BTU",
                                                   "std": 15.53, "status": "converted", "note": "converted from btu to kW", "unit_given": ""},
                                                  {"key": "burners", "label": "Burners", "unit": "count", "value": "6", "std": 6.0, "status": "verified"}],
             "parts_found": [{"part_no": "01.02.1005190"}]}
    s = benchmark.score(case, draft)
    assert (s["passed"], s["total"]) == (3, 4) and not s["checks"][3]["ok"]
    assert benchmark.run_file(b"%PDF-1.4 not a known file")["matched"] is False


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok ", name)
    print("Reader tests passed.")
