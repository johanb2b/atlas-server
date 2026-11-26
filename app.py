#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Webbgränssnittet för Atlas Server.

Servrarna dokumenteras i miljöer (en kund eller en del av en kunds nät). Filerna från insamlaren
importeras maskin för maskin i en miljö, och därifrån byggs Word och Excel. Webben kontaktar aldrig
servrarna själv. Inloggning, HTTPS och skydd mot CSRF är desamma som i Atlas.

Datakatalogen (ATLAS_SERVER_DATA, i Docker /data):
    envs/<id>/env.json           miljöns namn, kund och dokumentuppgifter
    envs/<id>/servers/<NAMN>.json  senaste filen från insamlaren för servern
    envs/<id>/notes.json         beskrivning och ansvarig per server, skrivna i webben
    envs/<id>/logo.png|jpg       kundens logotyp
    settings.json, partner.*     partnerns uppgifter och logotyp, gemensamma för alla miljöer
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
import re
import secrets
import shutil
import sys
import threading
import time
import zipfile
from pathlib import Path

from flask import Flask, jsonify, redirect, request, send_file

import server_docx
import server_model as model
import server_xlsx

ROOT = Path(__file__).resolve().parent


def default_data_dir():
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "AtlasServer"
    return ROOT / "data"


DATA = Path(os.environ.get("ATLAS_SERVER_DATA") or default_data_dir()).resolve()
ENVS = DATA / "envs"
SETTINGS_FILE = DATA / "settings.json"
APP_USER = os.environ.get("APP_USER") or "admin"
DEFAULT_PASSWORD = "admin"
ENV_PASSWORD = os.environ.get("APP_PASSWORD") or ""
PASSWORD_LOCKED = bool(ENV_PASSWORD)
ENV_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
SERVER_RE = re.compile(r"^[A-Za-z0-9._-]{1,63}$")
MAX_FILE = 20 * 1024 * 1024
LOGO_MAX = 1024 * 1024

try:
    ENVS.mkdir(parents=True, exist_ok=True)
except OSError as e:
    sys.exit(f"FEL: kan inte skriva i datakatalogen {DATA} ({e.strerror}). Kontrollera volymen och att "
             f"användaren som kör appen har skrivrätt, eller ange en annan katalog med ATLAS_SERVER_DATA.")

app = Flask(__name__, static_folder="static", static_url_path="/static")
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024
app.json.ensure_ascii = False


def read_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def body():
    return request.get_json(force=True, silent=True) or {}


def clean_text(v, n):
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", str(v or "")).strip()[:n]


# =============================================================================
# Inloggning (samma som i Atlas)
# =============================================================================
# Två lägen här: APP_PASSWORD satt (kan inte bytas i webben), eller ett lösenord bytt i webben.
# Annars standardlösenordet admin, som måste bytas vid första inloggningen.

AUTH_FILE = DATA / "auth.json"
PBKDF2_ROUNDS = 600_000
UI_COOKIE = "atlas_server_session"
UI_IDLE = 8 * 3600       # utloggad efter åtta timmar utan aktivitet
UI_MAX = 7 * 24 * 3600   # och senast efter en vecka
MIN_PASSWORD = 8
UI_SESSIONS = {}
FAILED = {}              # IP-adress: tider för misslyckade inloggningar
FAIL_LIMIT, FAIL_WINDOW = 5, 300
AUTH_LOCK = threading.Lock()
_VERIFIED = {}           # (användare, sha256 av lösenordet): hashens version, så att Basic auth inte räknar om PBKDF2


def hash_password(pw, salt=None, rounds=PBKDF2_ROUNDS):
    salt = salt or secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), salt, rounds)
    return f"pbkdf2_sha256${rounds}${salt.hex()}${dk.hex()}"


def check_hash(pw, stored):
    try:
        algo, rounds, salt, dk = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        return secrets.compare_digest(hash_password(pw, bytes.fromhex(salt), int(rounds)), stored)
    except (ValueError, AttributeError):
        return False


def stored_auth():
    a = read_json(AUTH_FILE, {})
    return a if isinstance(a, dict) and str(a.get("hash", "")).startswith("pbkdf2_sha256$") else None


def auth_mode():
    """'env' (APP_PASSWORD), 'stored' (bytt i webben) eller 'default' (måste bytas)."""
    if PASSWORD_LOCKED:
        return "env"
    return "stored" if stored_auth() else "default"


def must_change():
    return auth_mode() == "default"


def check_login(user, pw):
    if not secrets.compare_digest((user or "").encode(), APP_USER.encode()):
        return False
    pw = pw or ""
    mode = auth_mode()
    if mode == "env":
        return secrets.compare_digest(pw.encode(), ENV_PASSWORD.encode())
    if mode == "default":
        return secrets.compare_digest(pw.encode(), DEFAULT_PASSWORD.encode())
    stored = stored_auth()["hash"]
    key = (user, hashlib.sha256(pw.encode()).hexdigest())
    with AUTH_LOCK:
        if _VERIFIED.get(key) == stored:
            return True
    ok = check_hash(pw, stored)
    if ok:
        with AUTH_LOCK:
            _VERIFIED.clear()
            _VERIFIED[key] = stored
    return ok


def client_ip():
    return request.remote_addr or "?"


def throttled():
    now = time.time()
    with AUTH_LOCK:
        times = [x for x in FAILED.get(client_ip(), []) if now - x < FAIL_WINDOW]
        FAILED[client_ip()] = times
        return len(times) >= FAIL_LIMIT


def note_failure():
    with AUTH_LOCK:
        FAILED.setdefault(client_ip(), []).append(time.time())


def ui_session():
    sid = request.cookies.get(UI_COOKIE) or ""
    now = time.time()
    with AUTH_LOCK:
        s = UI_SESSIONS.get(sid)
        if not s:
            return None
        if now - s["last"] > UI_IDLE or now - s["created"] > UI_MAX:
            UI_SESSIONS.pop(sid, None)
            return None
        s["last"] = now
        return s


def new_ui_session(resp):
    sid = secrets.token_urlsafe(32)
    now = time.time()
    with AUTH_LOCK:
        for k in [k for k, v in UI_SESSIONS.items() if now - v["last"] > UI_IDLE or now - v["created"] > UI_MAX]:
            UI_SESSIONS.pop(k, None)
        UI_SESSIONS[sid] = {"user": APP_USER, "created": now, "last": now}
    resp.set_cookie(UI_COOKIE, sid, httponly=True, samesite="Strict", secure=request.is_secure, path="/",
                    max_age=UI_MAX)
    return resp


def authenticated():
    """Inloggad med sessionskaka (webbläsaren) eller Basic auth (skript)."""
    if ui_session():
        return True
    creds = basic_credentials()
    if creds:
        if throttled():
            return False
        if any(check_login(u, p) for u, p in creds):
            return True
        note_failure()
    return False


def basic_credentials():
    """Användare och lösenord ur Basic auth. Klienter kodar å, ä och ö olika (UTF-8 eller Latin-1), så båda prövas."""
    head = request.headers.get("Authorization") or ""
    if not head[:6].lower() == "basic ":
        return []
    try:
        raw = base64.b64decode(head[6:].strip(), validate=True)
    except ValueError:
        return []
    out = []
    for enc in ("utf-8", "latin-1"):
        try:
            user, sep, pw = raw.decode(enc).partition(":")
        except UnicodeDecodeError:
            continue
        if sep and (user, pw) not in out:
            out.append((user, pw))
    return out


# Det som går att nå utan inloggning: inloggningssidan och det den behöver.
PUBLIC = {"/healthz", "/login", "/api/login", "/api/me", "/static/login.js", "/static/app.css", "/static/theme.js",
          "/static/favicon.svg", "/static/login.html"}
# Det som går att nå med standardlösenordet, innan det har bytts.
BEFORE_CHANGE = {"/api/me", "/api/password", "/api/logout"}


# =============================================================================
# Skydd: valfri inloggning, CSRF-spärr och säkerhetshuvuden
# =============================================================================

@app.before_request
def guard():
    path = request.path
    if request.method not in ("GET", "HEAD") and request.headers.get("X-Atlas-Server") != "1":
        return jsonify(error=T("Anropet saknar rätt huvud.", "The request is missing the required header.")), 403
    if path in PUBLIC:
        return None
    if not authenticated():
        if path.startswith("/api/"):
            return jsonify(error=T("Inloggning krävs.", "Login required."), login=True), 401
        return redirect(f"{login_prefix()}login")
    if must_change() and path not in BEFORE_CHANGE:
        if path.startswith("/api/"):
            return jsonify(error=T("Byt standardlösenordet innan du fortsätter.",
                                   "Change the default password before you continue."), must_change=True), 403
        return redirect(f"{login_prefix()}login")
    return None


def login_prefix():
    """Relativ väg till sidroten, så att omdirigeringen fungerar bakom en proxy på en undersökväg."""
    return "../" * max(0, request.path.count("/") - 1)


@app.after_request
def headers(resp):
    resp.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
        "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "no-referrer"
    if request.path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-store"
    return resp




def ui_lang():
    lang = request.headers.get("X-Lang") or request.args.get("lang") or request.cookies.get("as_lang") or ""
    return lang if lang in model.LANGS else "sv"


def T(sv, en):
    return en if ui_lang() == "en" else sv


def err(msg, code=400):
    return jsonify(error=msg), code


@app.get("/")
def index():
    return app.send_static_file("index.html")


@app.get("/api/info")
def info():
    return jsonify(version=model.VERSION, data=str(DATA))


# =============================================================================
# Miljöer
# =============================================================================

def env_dir(eid):
    if not ENV_ID_RE.fullmatch(eid or ""):
        return None
    p = ENVS / eid
    return p if (p / "env.json").is_file() else None


def slug(name):
    s = name.lower()
    for a, b in (("å", "a"), ("ä", "a"), ("ö", "o"), ("é", "e"), ("ü", "u")):
        s = s.replace(a, b)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:40] or "miljo"
    base, n = s, 2
    while (ENVS / s).exists():
        s = f"{base}-{n}"
        n += 1
    return s


ENV_FIELDS = {"name": 80, "customer": 120, "version": 20, "owner": 120, "approver": 120}


def clean_env(b, old=None):
    e = dict(old or {})
    for k, n in ENV_FIELDS.items():
        if k in b:
            e[k] = clean_text(b.get(k), n)
    if "classification" in b:
        c = b.get("classification")
        e["classification"] = c if c in server_docx.CLASSIFICATIONS else "internal"
    if "hide_services" in b:
        names = b.get("hide_services")
        if isinstance(names, str):
            names = re.split(r"[\s,;]+", names)
        e["hide_services"] = sorted({clean_text(x, 100) for x in names or [] if clean_text(x, 100)})[:500]
    for k in ("show_software", "show_all_features"):
        if k in b:
            e[k] = bool(b.get(k))
    return e


def env_servers(p):
    out = {}
    for f in sorted((p / "servers").glob("*.json")):
        try:
            out[f.stem] = model.load_raw(f)
        except (model.FormatError, OSError):
            continue
    return out


def built_servers(p, env, lang):
    notes = read_json(p / "notes.json", {})
    hidden = env.get("hide_services") or []
    return [model.build_server(raw, lang, notes.get(name), hidden) for name, raw in env_servers(p).items()]


def env_payload(eid, p, lang, with_servers=True):
    env = read_json(p / "env.json", {})
    out = dict(env, id=eid, logo=logo_file(p) is not None)
    out.setdefault("classification", "internal")
    out.setdefault("version", "1.0")
    out.setdefault("show_software", True)
    out.setdefault("show_all_features", True)
    out.setdefault("hide_services", [])
    servers = built_servers(p, env, lang)
    out["count"] = len(servers)
    if with_servers:
        out["servers"] = [model.server_summary(s, lang) for s in model.sort_servers(servers)]
        out["observations"] = [o for s in servers for o in model.observations(s, lang)]
    else:
        out["updated"] = max((s["meta"]["collected"] for s in servers), default="")
    return out


@app.get("/api/envs")
def list_envs():
    out = []
    for d in sorted(ENVS.iterdir()) if ENVS.is_dir() else []:
        if (d / "env.json").is_file():
            out.append(env_payload(d.name, d, ui_lang(), with_servers=False))
    out.sort(key=lambda e: (e.get("customer") or "", e.get("name") or "").__str__().lower())
    return jsonify(envs=out, classifications=[{"value": k, "label": server_docx.classification_label(k, ui_lang())}
                                              for k in server_docx.CLASSIFICATIONS])


@app.post("/api/envs")
def create_env():
    b = body()
    name = clean_text(b.get("name"), 80)
    if not name:
        return err(T("Ange ett namn på miljön.", "Enter a name for the environment."))
    eid = slug(f"{clean_text(b.get('customer'), 40)} {name}".strip())
    p = ENVS / eid
    (p / "servers").mkdir(parents=True, exist_ok=True)
    env = clean_env(b)
    env["created"] = time.strftime("%Y-%m-%d")
    write_json(p / "env.json", env)
    return jsonify(id=eid), 201


@app.get("/api/envs/<eid>")
def get_env(eid):
    p = env_dir(eid)
    if not p:
        return err(T("Miljön finns inte.", "The environment does not exist."), 404)
    return jsonify(env_payload(eid, p, ui_lang()))


@app.put("/api/envs/<eid>")
def put_env(eid):
    p = env_dir(eid)
    if not p:
        return err(T("Miljön finns inte.", "The environment does not exist."), 404)
    env = clean_env(body(), read_json(p / "env.json", {}))
    if not env.get("name"):
        return err(T("Ange ett namn på miljön.", "Enter a name for the environment."))
    write_json(p / "env.json", env)
    return jsonify(env_payload(eid, p, ui_lang(), with_servers=False))


@app.delete("/api/envs/<eid>")
def delete_env(eid):
    p = env_dir(eid)
    if not p:
        return err(T("Miljön finns inte.", "The environment does not exist."), 404)
    shutil.rmtree(p)
    return jsonify(ok=True)


# =============================================================================
# Import av filer från insamlaren
# =============================================================================

def import_one(p, filename, data):
    """Importerar en fil. Returnerar en rad för svaret, med ok, server och meddelande."""
    try:
        raw = model.load_raw(data)
    except model.FormatError as e:
        return {"file": filename, "ok": False,
                "message": T(f"Kan inte läsas: {e}.", f"Cannot be read: {e}.")}
    name = model.server_name(raw)
    target = p / "servers" / f"{name}.json"
    old = None
    if target.is_file():
        try:
            old = model.load_raw(target)
        except model.FormatError:
            old = None
    new_t = raw["_meta"].get("collected_utc") or ""
    if old and (old["_meta"].get("collected_utc") or "") > new_t:
        return {"file": filename, "ok": False, "server": name,
                "message": T("Det finns redan en nyare insamling av servern. Filen hoppades över.",
                             "A newer collection of the server already exists. The file was skipped.")}
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, target)
    return {"file": filename, "ok": True, "server": name, "replaced": old is not None,
            "message": T("Uppdaterad.", "Updated.") if old else T("Importerad.", "Imported.")}


@app.post("/api/envs/<eid>/import")
def import_files(eid):
    p = env_dir(eid)
    if not p:
        return err(T("Miljön finns inte.", "The environment does not exist."), 404)
    files = request.files.getlist("files")
    if not files:
        return err(T("Välj en eller flera filer från insamlaren.", "Choose one or more files from the collector."))
    results = []
    for f in files:
        fname = Path(f.filename or "fil").name
        data = f.read(MAX_FILE + 1)
        if len(data) > MAX_FILE:
            results.append({"file": fname, "ok": False, "message": T("Filen är för stor.", "The file is too large.")})
            continue
        if data[:2] == b"PK":
            # En zip med JSON-filerna, till exempel hela mappen output från insamlaren.
            try:
                with zipfile.ZipFile(io.BytesIO(data)) as z:
                    names = [n for n in z.namelist() if n.lower().endswith(".json") and not n.endswith("/")]
                    if not names:
                        results.append({"file": fname, "ok": False,
                                        "message": T("Zip-filen innehåller inga JSON-filer.",
                                                     "The zip file contains no JSON files.")})
                    for n in names[:500]:
                        info_ = z.getinfo(n)
                        if info_.file_size > MAX_FILE:
                            results.append({"file": n, "ok": False,
                                            "message": T("Filen är för stor.", "The file is too large.")})
                            continue
                        results.append(import_one(p, f"{fname}: {Path(n).name}", z.read(n)))
            except zipfile.BadZipFile:
                results.append({"file": fname, "ok": False,
                                 "message": T("Zip-filen är trasig.", "The zip file is corrupt.")})
            continue
        results.append(import_one(p, fname, data))
    ok = sum(1 for r in results if r["ok"])
    return jsonify(results=results, imported=ok, failed=len(results) - ok)


# =============================================================================
# Servrar
# =============================================================================

def server_file(p, name):
    if not SERVER_RE.fullmatch(name or ""):
        return None
    f = p / "servers" / f"{name.upper()}.json"
    return f if f.is_file() else None


@app.get("/api/envs/<eid>/servers/<name>")
def get_server(eid, name):
    p = env_dir(eid)
    f = server_file(p, name) if p else None
    if not f:
        return err(T("Servern finns inte.", "The server does not exist."), 404)
    env = read_json(p / "env.json", {})
    lang = ui_lang()
    s = model.build_server(model.load_raw(f), lang, read_json(p / "notes.json", {}).get(f.stem),
                           env.get("hide_services") or [])
    s["observations"] = model.observations(s, lang)
    return jsonify(s)


@app.put("/api/envs/<eid>/servers/<name>/note")
def put_note(eid, name):
    p = env_dir(eid)
    f = server_file(p, name) if p else None
    if not f:
        return err(T("Servern finns inte.", "The server does not exist."), 404)
    b = body()
    notes = read_json(p / "notes.json", {})
    notes[f.stem] = {"description": clean_text(b.get("description"), 400), "owner": clean_text(b.get("owner"), 120)}
    write_json(p / "notes.json", notes)
    return jsonify(ok=True)


@app.delete("/api/envs/<eid>/servers/<name>")
def delete_server(eid, name):
    p = env_dir(eid)
    f = server_file(p, name) if p else None
    if not f:
        return err(T("Servern finns inte.", "The server does not exist."), 404)
    f.unlink()
    notes = read_json(p / "notes.json", {})
    if notes.pop(f.stem, None) is not None:
        write_json(p / "notes.json", notes)
    return jsonify(ok=True)


# =============================================================================
# Inställningar: partnerns uppgifter och logotyper
# =============================================================================

PARTNER_FIELDS = ("company", "consultant", "email", "phone")


def load_settings():
    s = read_json(SETTINGS_FILE, {})
    p = s.get("partner") if isinstance(s.get("partner"), dict) else {}
    return {"partner": {k: clean_text(p.get(k), 120) for k in PARTNER_FIELDS}}


@app.get("/api/settings")
def get_settings():
    return jsonify(dict(load_settings(), partner_logo=logo_file(DATA, "partner") is not None))


@app.put("/api/settings")
def put_settings():
    b = body()
    p = b.get("partner") if isinstance(b.get("partner"), dict) else {}
    s = {"partner": {k: clean_text(p.get(k), 120) for k in PARTNER_FIELDS}}
    write_json(SETTINGS_FILE, s)
    return jsonify(s)


def logo_file(folder, stem="logo"):
    for ext in ("png", "jpg"):
        f = Path(folder) / f"{stem}.{ext}"
        if f.is_file():
            return f
    return None


def save_logo(folder, stem):
    f = request.files.get("file")
    data = f.read(LOGO_MAX + 1) if f else b""
    if not data:
        return err(T("Välj en bild.", "Choose an image."))
    if len(data) > LOGO_MAX:
        return err(T("Bilden får vara högst 1 MB.", "The image may be at most 1 MB."))
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        ext = "png"
    elif data[:3] == b"\xff\xd8\xff":
        ext = "jpg"
    else:
        return err(T("Bilden ska vara PNG eller JPEG.", "The image must be PNG or JPEG."))
    if not server_docx.image_size(data):
        return err(T("Bilden kan inte läsas.", "The image cannot be read."))
    for old in (Path(folder) / f"{stem}.png", Path(folder) / f"{stem}.jpg"):
        old.unlink(missing_ok=True)
    (Path(folder) / f"{stem}.{ext}").write_bytes(data)
    return jsonify(ok=True)


@app.route("/api/logo/partner", methods=["GET", "PUT", "DELETE"])
def partner_logo():
    return logo_route(DATA, "partner")


@app.route("/api/envs/<eid>/logo", methods=["GET", "PUT", "DELETE"])
def env_logo(eid):
    p = env_dir(eid)
    if not p:
        return err(T("Miljön finns inte.", "The environment does not exist."), 404)
    return logo_route(p, "logo")


def logo_route(folder, stem):
    if request.method == "PUT":
        return save_logo(folder, stem)
    f = logo_file(folder, stem)
    if request.method == "DELETE":
        if f:
            f.unlink()
        return jsonify(ok=True)
    if not f:
        return err(T("Ingen logotyp.", "No logo."), 404)
    return send_file(f, mimetype="image/png" if f.suffix == ".png" else "image/jpeg", max_age=0)


def logo_data(folder, stem):
    f = logo_file(folder, stem)
    return {"data": f.read_bytes()} if f else None


# =============================================================================
# Export
# =============================================================================

@app.get("/api/envs/<eid>/export/<kind>")
def export(eid, kind):
    p = env_dir(eid)
    if not p:
        return err(T("Miljön finns inte.", "The environment does not exist."), 404)
    lang = request.args.get("lang") if request.args.get("lang") in model.LANGS else ui_lang()
    env = read_json(p / "env.json", {})
    servers = built_servers(p, env, lang)
    if kind in ("docx", "xlsx") and not servers:
        return err(T("Importera minst en server först.", "Import at least one server first."), 409)
    customer = env.get("customer") or env.get("name") or ""
    if kind == "docx":
        info_ = server_docx.default_info(
            lang, customer=env.get("customer"), system=env.get("name"), version=env.get("version"),
            classification=env.get("classification"), owner=env.get("owner"), approver=env.get("approver"),
            partner=load_settings()["partner"],
            logos={"customer": logo_data(p, "logo"), "partner": logo_data(DATA, "partner")})
        data = server_docx.to_docx(server_docx.build_doc(servers, lang, info_,
                                                         show_software=env.get("show_software", True),
                                                         show_all_features=env.get("show_all_features", True)))
        name = server_docx.file_name(customer, "docx", lang)
        mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    elif kind == "xlsx":
        data = server_xlsx.to_xlsx(servers, lang)
        name = server_docx.file_name(customer, "xlsx", lang)
        mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    elif kind == "zip":
        # Alla filer från insamlaren, så att miljön kan flyttas till en annan Atlas Server.
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for f in sorted((p / "servers").glob("*.json")):
                z.write(f, f"atlasserver_{f.name}")
        data, name, mime = buf.getvalue(), f"{eid}_insamling.zip", "application/zip"
    else:
        return err(T("Okänt format.", "Unknown format."), 404)
    return send_file(io.BytesIO(data), mimetype=mime, as_attachment=True, download_name=name)


@app.get("/api/collector")
def collector():
    """Insamlaren som zip, så att den kan hämtas direkt från webben och kopieras till servrarna."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted((ROOT / "collector").iterdir()):
            if f.is_file():
                z.write(f, f"AtlasServer-Collector/{f.name}")
    return send_file(io.BytesIO(buf.getvalue()), mimetype="application/zip", as_attachment=True,
                     download_name=f"AtlasServer-Collector-{model.VERSION}.zip")


@app.get("/login")
def login_page():
    if authenticated() and not must_change():
        return redirect("./")
    return app.send_static_file("login.html")


def login_state():
    return {"user": APP_USER, "must_change": must_change(), "locked": PASSWORD_LOCKED, "min_length": MIN_PASSWORD}


@app.post("/api/login")
def api_login():
    if throttled():
        return err(T("För många misslyckade försök. Vänta fem minuter och försök igen.",
                     "Too many failed attempts. Wait five minutes and try again."), 429)
    b = body()
    if not check_login(str(b.get("user") or ""), str(b.get("password") or "")):
        note_failure()
        time.sleep(0.5)
        return err(T("Fel användarnamn eller lösenord.", "Wrong user name or password."), 401)
    with AUTH_LOCK:
        FAILED.pop(client_ip(), None)
    return new_ui_session(jsonify(login_state()))


@app.post("/api/logout")
def api_logout():
    with AUTH_LOCK:
        UI_SESSIONS.pop(request.cookies.get(UI_COOKIE) or "", None)
    resp = jsonify(ok=True)
    resp.delete_cookie(UI_COOKIE, path="/")
    return resp


@app.get("/api/me")
def api_me():
    """Inloggningens läge. Nås utan inloggning, men säger då bara att ingen är inloggad."""
    if not authenticated():
        return jsonify(authenticated=False)
    return jsonify(dict(login_state(), authenticated=True))


def password_problem(new, confirm):
    if PASSWORD_LOCKED:
        return T("Lösenordet styrs av APP_PASSWORD och kan inte bytas här. Ändra miljövariabeln och starta om Atlas Server.",
                 "The password is set by APP_PASSWORD and cannot be changed here. Change the environment variable "
                 "and restart Atlas Server.")
    if new != confirm:
        return T("Lösenorden är inte lika.", "The passwords do not match.")
    if len(new) < MIN_PASSWORD:
        return T(f"Lösenordet måste ha minst {MIN_PASSWORD} tecken.",
                 f"The password must have at least {MIN_PASSWORD} characters.")
    if new.casefold() in {DEFAULT_PASSWORD, APP_USER.casefold()}:
        return T("Välj ett annat lösenord än standardlösenordet och användarnamnet.",
                 "Choose a password other than the default password and the user name.")
    return None


@app.post("/api/password")
def api_password():
    b = body()
    current, new, confirm = (str(b.get(k) or "") for k in ("current", "new", "confirm"))
    if throttled():
        return err(T("För många misslyckade försök. Vänta fem minuter och försök igen.",
                     "Too many failed attempts. Wait five minutes and try again."), 429)
    if not check_login(APP_USER, current):
        note_failure()
        return err(T("Det nuvarande lösenordet är fel.", "The current password is wrong."), 403)
    problem = password_problem(new, confirm)
    if problem:
        return err(problem, 409 if PASSWORD_LOCKED else 400)
    write_json(AUTH_FILE, {"user": APP_USER, "hash": hash_password(new),
                           "changed": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
    try:
        os.chmod(AUTH_FILE, 0o600)
    except OSError:
        pass
    with AUTH_LOCK:  # alla andra inloggningar slutar gälla
        UI_SESSIONS.clear()
        _VERIFIED.clear()
    return new_ui_session(jsonify(login_state()))


@app.get("/healthz")
def healthz():
    return "ok"


def parse_port(value, source):
    try:
        port = int(str(value).strip())
    except ValueError:
        port = 0
    if not 1 <= port <= 65535:
        sys.exit(f"FEL: ogiltig port {value!r} i {source}. Ange ett tal mellan 1 och 65535.")
    return port


# =============================================================================
# HTTPS
# =============================================================================
# Waitress kan inte TLS. Med HTTPS används i stället servern i Werkzeug, som följer med Flask.
# Handskakningen görs i tråden för varje anslutning, så att en långsam klient inte stoppar andra.
# Vanlig http till samma port får en omdirigering till https.

TLS_DIR = DATA / "tls"
TLS_HANDSHAKE_TIMEOUT = 15   # sekunder för handskakningen
TLS_IDLE_TIMEOUT = 120       # sekunder utan trafik innan en anslutning stängs


def tls_names():
    """Namn och adresser i det självsignerade certifikatet: localhost, datorns namn och TLS_NAMES."""
    import ipaddress
    import socket
    names = ["localhost", "127.0.0.1"]
    for v in re.split(r"[,\s]+", " ".join([os.environ.get("TLS_NAMES", ""), os.environ.get("BIND_ADDRESS", "")])):
        if v and v not in ("0.0.0.0", "::"):
            names.append(v)
    names.append(socket.gethostname())
    out = []
    for n in names:
        n = n.strip().strip("[]")
        if not n:
            continue
        try:
            entry = f"IP:{ipaddress.ip_address(n)}"
        except ValueError:
            if not re.fullmatch(r"[A-Za-z0-9*]([A-Za-z0-9.-]*[A-Za-z0-9])?", n):
                continue
            entry = f"DNS:{n}"
        if entry not in out:
            out.append(entry)
    return out


def make_self_signed(cert, key):
    """Skapar ett självsignerat certifikat med openssl. Nyckeln får bara läsas av ägaren."""
    import subprocess
    exe = shutil.which("openssl")
    if not exe:
        sys.exit("FEL: TLS=auto kräver programmet openssl för att skapa certifikatet, och det finns inte här. "
                 "Ange egna filer med TLS_CERT och TLS_KEY, eller stäng av HTTPS med TLS=off.")
    cert.parent.mkdir(parents=True, exist_ok=True)
    names = tls_names()
    cn = next((n.split(":", 1)[1] for n in names if n.startswith("DNS:") and n != "DNS:localhost"), "atlas-server")
    tmp_key, tmp_cert = key.with_suffix(".key.tmp"), cert.with_suffix(".crt.tmp")
    old = os.umask(0o077)
    try:
        r = subprocess.run([exe, "req", "-x509", "-newkey", "rsa:3072", "-sha256", "-days", "825", "-nodes",
                            "-keyout", str(tmp_key), "-out", str(tmp_cert), "-subj", f"/CN={cn}/O=Atlas Server",
                            "-addext", "subjectAltName=" + ",".join(names),
                            "-addext", "extendedKeyUsage=serverAuth"],
                           capture_output=True, text=True, timeout=120)
    finally:
        os.umask(old)
    if r.returncode != 0:
        for f in (tmp_key, tmp_cert):
            f.unlink(missing_ok=True)
        sys.exit(f"FEL: openssl kunde inte skapa certifikatet: {(r.stderr or r.stdout).strip()[-300:]}")
    os.chmod(tmp_key, 0o600)
    os.chmod(tmp_cert, 0o644)
    tmp_key.replace(key)
    tmp_cert.replace(cert)
    print(f"Skapade ett självsignerat certifikat för {', '.join(n.split(':', 1)[1] for n in names)} i {cert.parent}. "
          f"Byt det genom att ersätta {cert.name} och {key.name}.", flush=True)


def tls_files():
    """(certifikat, nyckel) om HTTPS ska användas, annars None. TLS_CERT och TLS_KEY går före TLS=auto."""
    cert, key = os.environ.get("TLS_CERT"), os.environ.get("TLS_KEY")
    if cert or key:
        if not (cert and key):
            sys.exit("FEL: ange både TLS_CERT och TLS_KEY.")
        cert, key = Path(cert).expanduser(), Path(key).expanduser()
        for f, name in ((cert, "TLS_CERT"), (key, "TLS_KEY")):
            if not f.is_file():
                sys.exit(f"FEL: filen i {name} finns inte: {f}")
        return cert, key
    mode = (os.environ.get("TLS") or "off").strip().lower()
    if mode in ("", "off", "0", "false", "nej", "no"):
        return None
    if mode not in ("auto", "on", "1", "true", "ja", "yes"):
        sys.exit(f"FEL: TLS ska vara auto eller off, inte {mode}.")
    cert, key = TLS_DIR / "atlas-server.crt", TLS_DIR / "atlas-server.key"
    if not (cert.is_file() and key.is_file()):
        make_self_signed(cert, key)
    return cert, key


def tls_context(cert, key):
    import ssl
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    try:
        ctx.load_cert_chain(str(cert), str(key))
    except (ssl.SSLError, OSError) as e:
        sys.exit(f"FEL: certifikatet eller nyckeln kan inte läsas ({cert}, {key}): {e}. "
                 "Filerna ska vara i PEM-format och nyckeln får inte ha lösenord.")
    return ctx


def make_tls_server(host, port, ctx):
    import socket
    import ssl

    from werkzeug.serving import ThreadedWSGIServer, WSGIRequestHandler

    class Handler(WSGIRequestHandler):
        def log_request(self, code="-", size="-"):
            pass  # som waitress: ingen rad per anrop

    class TLSServer(ThreadedWSGIServer):
        def finish_request(self, request, client_address):
            request.settimeout(TLS_HANDSHAKE_TIMEOUT)
            try:
                head = request.recv(8, socket.MSG_PEEK)
            except OSError:
                return
            if head[:1].isalpha():
                self.redirect_http(request)
                return
            try:
                conn = ctx.wrap_socket(request, server_side=True)
            except (ssl.SSLError, OSError):
                return
            try:
                conn.settimeout(TLS_IDLE_TIMEOUT)
                self.RequestHandlerClass(conn, client_address, self)
            except (ssl.SSLError, OSError):
                pass
            finally:
                try:
                    conn.close()
                except OSError:
                    pass

        def redirect_http(self, request):
            """Vanlig http till https-porten: omdirigera till samma sida över https."""
            data = b""
            try:
                while b"\r\n\r\n" not in data and len(data) < 8192:
                    chunk = request.recv(4096)
                    if not chunk:
                        break
                    data += chunk
            except OSError:
                return
            text = data.decode("latin-1", "replace")
            first = text.split("\r\n", 1)[0].split(" ")
            path = first[1] if len(first) > 1 and first[1].startswith("/") else "/"
            m = re.search(r"(?im)^host:\s*([A-Za-z0-9.\-:\[\]]+)\s*$", text)
            hostport = m.group(1) if m else f"{host}:{port}"
            if not re.fullmatch(r"[^\s\x00-\x1f]*", path):
                path = "/"
            body = b"Atlas Server anv\xc3\xa4nder https.\n"
            try:
                request.sendall((f"HTTP/1.1 301 Moved Permanently\r\nLocation: https://{hostport}{path}\r\n"
                                 f"Content-Type: text/plain; charset=utf-8\r\nContent-Length: {len(body)}\r\n"
                                 "Connection: close\r\n\r\n").encode("latin-1") + body)
            except OSError:
                pass

    try:
        server = TLSServer(host, port, app, handler=Handler)
    except SystemExit:
        sys.exit(f"FEL: kan inte lyssna på {host}:{port}. Porten används troligen redan. "
                 f"Välj en annan med PORT eller --port.")
    server.ssl_context = ctx  # ger wsgi.url_scheme https, så att kakan blir Secure
    return server



def main(argv=None):
    p = argparse.ArgumentParser(prog="app.py", description="Webbgränssnittet för Atlas Server.")
    p.add_argument("--port", help="Port att lyssna på. Standard: miljövariabeln PORT, annars 8090")
    p.add_argument("--host", help="Adress att lyssna på. Standard: miljövariabeln HOST, annars 127.0.0.1")
    p.add_argument("--open", action="store_true", help="Öppna gränssnittet i webbläsaren när servern har startat")
    a = p.parse_args(argv)
    if a.port:
        port = parse_port(a.port, "--port")
    elif os.environ.get("PORT"):
        port = parse_port(os.environ["PORT"], "miljövariabeln PORT")
    else:
        port = 8090
    host = a.host or os.environ.get("HOST") or "127.0.0.1"

    files = tls_files()
    scheme = "https" if files else "http"
    if files:
        server = make_tls_server(host, port, tls_context(*files))
        run = server.serve_forever
    else:
        from waitress import create_server
        try:
            server = create_server(app, host=host, port=port, threads=8)
        except OSError as e:
            sys.exit(f"FEL: kan inte lyssna på {host}:{port} ({e.strerror or e}). Porten används troligen redan. "
                     f"Välj en annan med PORT eller --port.")
        run = server.run
    shown = f"[{host}]" if ":" in host else host
    print(f"Atlas Server {model.VERSION} lyssnar på {scheme}://{shown}:{port}  (data i {DATA})", flush=True)
    mode = auth_mode()
    if mode == "env":
        print(f"Inloggning: användare {APP_USER}, lösenordet i APP_PASSWORD.", flush=True)
    elif mode == "stored":
        print(f"Inloggning: användare {APP_USER}, lösenordet som bytts i webben ({AUTH_FILE}).", flush=True)
    else:
        print(f"Inloggning: användare {APP_USER}, lösenord {DEFAULT_PASSWORD}. Det måste bytas vid första "
              f"inloggningen.", flush=True)
    if a.open:
        import webbrowser
        local = "127.0.0.1" if host in ("0.0.0.0", "::", "") else host
        url = f"{scheme}://{'[' + local + ']' if ':' in local else local}:{port}/"
        threading.Timer(1.0, webbrowser.open, args=(url,)).start()
    try:
        run()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
