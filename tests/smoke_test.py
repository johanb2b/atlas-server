#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Röktest för Atlas Server: modellen, Word, Excel, kommandoraden och webben med exempelfilerna.

    python tests/smoke_test.py
"""
import io
import json
import os
import sys
import tempfile
import zipfile
from pathlib import Path
from xml.dom import minidom

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
DATA = ROOT / "tests" / "data"
TMP = Path(tempfile.mkdtemp(prefix="atlas-server-test-"))
os.environ["ATLAS_SERVER_DATA"] = str(TMP / "data")
os.environ.pop("APP_PASSWORD", None)

import server_docx  # noqa: E402
import server_model as m  # noqa: E402
import server_xlsx  # noqa: E402

FILES = sorted(DATA.glob("*.json"))
fails = []


def check(cond, what):
    print(("ok   " if cond else "FEL  ") + what)
    if not cond:
        fails.append(what)


def docx_ok(data):
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for n in z.namelist():
            if n.endswith(".xml") or n.endswith(".rels"):
                minidom.parseString(z.read(n))
        return z.read("word/document.xml").decode("utf-8")


# --- Modellen ------------------------------------------------------------------
check(len(FILES) == 3, "tre exempelfiler finns")
servers = {s["name"]: s for s in (m.build_server(m.load_raw(f), "sv") for f in FILES)}
dc, fs, app = servers["DC01"], servers["FS01"], servers["APP01"]
check(dc["is_dc"] and dc["release"] == "2025" and dc["install_type"] == "Server Core", "DC01 tolkas som DC, 2025, Core")
check(dc["roles_added"] == ["Active Directory Domain Services", "DNS Server"], "tillagda roller på DC01")
check("File Server" in fs["roles_added"], "rolltjänst under standardroll räknas som tillagd")
check(app["ipv4"] == ["10.10.10.31/24", "10.10.20.31/24"], "IP-adresser med prefix")
classes = {x["name"]: x["class"] for x in app["services"]}
check(classes["MSSQLSERVER"] == "microsoft" and classes["ExempelAffar"] == "thirdparty", "klassning av tillagda tjänster")
check(classes["W3SVC"] == "windows" and classes["edgeupdate"] == "windows" and classes["WinDefend"] == "windows",
      "Windows, Edge och Defender räknas som standard")
check(classes["CDPUserSvc_4a1b2"] == "windows", "användartjänster räknas som standard")
hid = m.build_server(m.load_raw(DATA / "atlasserver_FS01_20261126-101400.json"), "sv", hidden=["VMTools"])
check("VMTools" not in [x["name"] for x in hid["services_extra"]], "dolda tjänster tas bort ur tilläggen")
obs = m.observations(fs, "sv")
check(any("SMB 1.0" in o["text"] for o in obs), "SMB 1.0 ger en iakttagelse")
try:
    m.load_raw(b'{"_meta": {"tool": "Annat"}}')
    check(False, "fel verktyg avvisas")
except m.FormatError:
    check(True, "fel verktyg avvisas")
bom = b"\xef\xbb\xbf" + FILES[0].read_bytes()
check(m.server_name(m.load_raw(bom)) == "APP01", "UTF-8 med BOM läses")
check(m.server_name(m.load_raw(FILES[0].read_text(encoding="utf-8").encode("utf-16"))) == "APP01", "UTF-16 läses")

# --- Word och Excel ------------------------------------------------------------
for lang in m.LANGS:
    ss = [m.build_server(m.load_raw(f), lang) for f in FILES]
    info = server_docx.default_info(lang, customer="Exempel AB", system="Produktion")
    xml = docx_ok(server_docx.to_docx(server_docx.build_doc(ss, lang, info)))
    check("DC01" in xml and "Exempel Affärssystem" in xml, f"Word ({lang}) är giltig XML och har innehållet")
    check(("Tjänster utöver Windows standard" if lang == "sv" else "Services beyond the Windows defaults") in xml,
          f"Word ({lang}) har rätt språk")
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(server_xlsx.to_xlsx(ss, lang)))
    check(len(wb.sheetnames) == 10 and wb.worksheets[0].max_row == 4, f"Excel ({lang}) har tio flikar och tre servrar")

# --- Kommandoraden -------------------------------------------------------------
import atlas_server_cli  # noqa: E402
cwd = os.getcwd()
os.chdir(TMP)
atlas_server_cli.main(["build", str(DATA), "--customer", "Exempel AB", "--out", "cli"])
os.chdir(cwd)
check((TMP / "cli.docx").is_file() and (TMP / "cli.xlsx").is_file(), "kommandoraden skriver Word och Excel")

# --- Webben --------------------------------------------------------------------
import app as web  # noqa: E402

c = web.app.test_client()
H = {"X-Atlas-Server": "1", "X-Lang": "sv"}
check(c.get("/api/envs").status_code == 401, "API kräver inloggning")
check(c.post("/api/envs", json={"name": "x"}).status_code == 403, "POST utan huvudet nekas")
r = c.post("/api/login", json={"user": "admin", "password": "admin"}, headers=H)
check(r.status_code == 200 and r.get_json()["must_change"], "inloggning med standardlösenordet kräver byte")
check(c.get("/api/envs").status_code == 403, "inget fungerar före byte av lösenord")
r = c.post("/api/password", json={"current": "admin", "new": "Hemligt-123", "confirm": "Hemligt-123"}, headers=H)
check(r.status_code == 200, "lösenordet byts")
r = c.post("/api/envs", json={"name": "Produktion", "customer": "Exempel AB"}, headers=H)
eid = r.get_json()["id"]
check(r.status_code == 201 and eid == "exempel-ab-produktion", "miljön skapas")

buf = io.BytesIO()
with zipfile.ZipFile(buf, "w") as z:
    for f in FILES[1:]:
        z.write(f, f"output/{f.name}")
r = c.post(f"/api/envs/{eid}/import", headers=H, content_type="multipart/form-data", data={"files": [
    (io.BytesIO(FILES[0].read_bytes()), FILES[0].name), (io.BytesIO(buf.getvalue()), "output.zip"),
    (io.BytesIO(b"inte json"), "trasig.json")]})
res = r.get_json()
check(res["imported"] == 3 and res["failed"] == 1, "import av JSON, zip och en trasig fil")
old = json.loads(FILES[0].read_text(encoding="utf-8"))
old["_meta"]["collected_utc"] = "2020-01-01T00:00:00Z"
r = c.post(f"/api/envs/{eid}/import", headers=H, content_type="multipart/form-data",
           data={"files": [(io.BytesIO(json.dumps(old).encode()), "gammal.json")]})
check(r.get_json()["failed"] == 1, "äldre insamling ersätter inte en nyare")

env = c.get(f"/api/envs/{eid}").get_json()
check([s["name"] for s in env["servers"]] == ["APP01", "DC01", "FS01"], "miljön visar tre servrar")
r = c.put(f"/api/envs/{eid}/servers/dc01/note", json={"description": "Domänkontrollant", "owner": "IT"}, headers=H)
check(r.status_code == 200, "beskrivning sparas")
s = c.get(f"/api/envs/{eid}/servers/DC01").get_json()
check(s["description"] == "Domänkontrollant" and s["owner"] == "IT", "beskrivningen följer med servern")
check(c.get(f"/api/envs/{eid}/servers/..%2Fenv").status_code == 404, "ogiltigt servernamn ger 404")
r = c.put(f"/api/envs/{eid}", json={"version": "1.1", "hide_services": "VMTools\nSentinelAgent",
                                    "classification": "confidential"}, headers=H)
check(r.status_code == 200, "miljöns inställningar sparas")
png = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
       b"\x00\x00\x00\rIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82")
r = c.put(f"/api/envs/{eid}/logo", headers=H, content_type="multipart/form-data",
          data={"file": (io.BytesIO(png), "logo.png")})
check(r.status_code == 200, "kundens logotyp sparas")
c.put("/api/settings", json={"partner": {"company": "Partner AB", "consultant": "Anna"}}, headers=H)

r = c.get(f"/api/envs/{eid}/export/docx?lang=sv")
check(r.status_code == 200 and "serverdokumentation.docx" in r.headers["Content-Disposition"], "Word laddas ner")
xml = docx_ok(r.data)
check("Konfidentiell" in xml and "Partner AB" in xml and "Domänkontrollant" in xml and "VMTools" not in xml,
      "Word har klassning, partner, beskrivning och respekterar dolda tjänster")
with zipfile.ZipFile(io.BytesIO(r.data)) as z:
    check("word/media/customer.png" in z.namelist(), "logotypen finns i Word")
r = c.get(f"/api/envs/{eid}/export/xlsx?lang=en")
check(r.status_code == 200 and r.data[:2] == b"PK", "Excel laddas ner")
r = c.get(f"/api/envs/{eid}/export/zip")
with zipfile.ZipFile(io.BytesIO(r.data)) as z:
    check(len(z.namelist()) == 3, "zip med insamlade filer")
r = c.get("/api/collector")
with zipfile.ZipFile(io.BytesIO(r.data)) as z:
    names = z.namelist()
    check(any(n.endswith("Collect-AtlasServer.ps1") for n in names) and any(n.endswith(".cmd") for n in names),
          "insamlaren kan hämtas från webben")
check(c.delete(f"/api/envs/{eid}/servers/FS01", headers=H).status_code == 200, "server tas bort")
check(len(c.get(f"/api/envs/{eid}").get_json()["servers"]) == 2, "två servrar kvar")
check(c.delete(f"/api/envs/{eid}", headers=H).status_code == 200, "miljön tas bort")

# --- Insamlaren ----------------------------------------------------------------
ps1 = (ROOT / "collector" / "Collect-AtlasServer.ps1").read_bytes()
check(ps1[:3] == b"\xef\xbb\xbf", "PowerShell-skriptet har BOM, så att å, ä och ö visas rätt i Windows PowerShell 5.1")
text = ps1.decode("utf-8-sig")
check("Win32_Product" not in text.replace("inte Win32_Product", "").replace("anropar inte Win32_Product", ""),
      "insamlaren anropar inte Win32_Product")
for bad in ("Set-", "Remove-", "Install-", "Enable-", "Disable-", "Stop-Service", "Start-Service", "Restart-"):
    lines = [ln for ln in text.splitlines() if bad in ln and not ln.strip().startswith("#")
             and "Enable-PSRemoting" not in ln and "Set-StrictMode" not in ln
             and "Remove-TypeData" not in ln]
    check(not lines, f"insamlaren innehåller inte {bad}")

print()
if fails:
    print(f"{len(fails)} fel.")
    sys.exit(1)
print("Alla test gick igenom.")
