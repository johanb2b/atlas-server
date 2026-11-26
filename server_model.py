#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Modellen i Atlas Server: tolkar JSON-filerna från insamlaren till tabeller.

Flödet är som i Atlas: insamlare, JSON per server, modell (tabeller), Excel, Word och webb.
Ingenting här kontaktar servrarna. Allt byggs från filerna, så dokumentet kan byggas om
när som helst.

Vilka tjänster och roller som räknas som Windows standard avgörs här och inte i
insamlaren, så att reglerna kan ändras utan att servrarna samlas in igen.
"""
from __future__ import annotations

import ipaddress
import json
import re
from pathlib import Path

VERSION = "1.0.0"
TOOL = "Atlas Server"
FORMATS = {1}
LANGS = ("sv", "en")


def tr(lang, sv, en):
    return en if lang == "en" else sv


# =============================================================================
# Läsa och kontrollera en fil från insamlaren
# =============================================================================

class FormatError(ValueError):
    pass


def load_raw(data):
    """Läser en fil (bytes, str eller sökväg) och kontrollerar att den kommer från insamlaren."""
    if isinstance(data, Path):
        data = data.read_bytes()
    if isinstance(data, bytes):
        # Windows PowerShell skriver ibland UTF-8 med BOM eller UTF-16. Insamlaren skriver UTF-8 utan BOM.
        if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
            data = data.decode("utf-16")
        else:
            data = data.decode("utf-8-sig")
    try:
        raw = json.loads(data)
    except json.JSONDecodeError as e:
        raise FormatError(f"inte giltig JSON ({e.msg}, rad {e.lineno})")
    if not isinstance(raw, dict) or not isinstance(raw.get("_meta"), dict):
        raise FormatError("saknar _meta, filen kommer inte från insamlaren i Atlas Server")
    meta = raw["_meta"]
    if meta.get("tool") != TOOL:
        raise FormatError(f"fel verktyg i _meta.tool ({meta.get('tool')!r})")
    if meta.get("format") not in FORMATS:
        raise FormatError(f"okänt format {meta.get('format')!r}, uppdatera Atlas Server")
    name = (raw.get("system") or {}).get("computer_name")
    if not name or not re.fullmatch(r"[A-Za-z0-9._-]{1,63}", str(name)):
        raise FormatError("saknar ett giltigt datornamn i system.computer_name")
    return raw


def server_name(raw):
    return str(raw["system"]["computer_name"]).upper()


# =============================================================================
# Hjälpfunktioner
# =============================================================================

def lst(v):
    """Insamlaren skriver listor, men PowerShell kan ge null eller ett ensamt värde."""
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def gib(b):
    try:
        return round(int(b) / 1024 ** 3, 1)
    except (TypeError, ValueError):
        return None


def prefix_of(mask):
    """255.255.255.0 blir 24. IPv6 har redan prefixet som tal."""
    if not mask:
        return ""
    mask = str(mask)
    if mask.isdigit():
        return mask
    try:
        return str(ipaddress.IPv4Network(f"0.0.0.0/{mask}").prefixlen)
    except ValueError:
        return mask


def date_only(s):
    return str(s)[:10] if s else ""


def datetime_short(s):
    return str(s)[:16].replace("T", " ") if s else ""


def fnum(v, lang="sv", dec=1):
    """Decimalkomma och mellanslag som tusentalsavgränsare på svenska."""
    if v is None or v == "":
        return ""
    if isinstance(v, float) and dec:
        s = f"{v:,.{dec}f}"
    else:
        s = f"{int(round(float(v))):,}"
    if lang == "sv":
        s = s.replace(",", " ").replace(".", ",")
    return s


# =============================================================================
# Windows-version, domänroll och plattform
# =============================================================================

# Byggnummer till Windows Server-version. Kontrollerade mot Microsofts versionsförteckning.
BUILDS = {
    "9600": "2012 R2", "14393": "2016", "17763": "2019", "20348": "2022", "26100": "2025",
}

DOMAIN_ROLES = {
    0: ("Fristående arbetsstation", "Standalone workstation"),
    1: ("Medlemsarbetsstation", "Member workstation"),
    2: ("Fristående server", "Standalone server"),
    3: ("Medlemsserver", "Member server"),
    4: ("Domänkontrollant", "Domain controller"),
    5: ("Domänkontrollant (PDC-emulator)", "Domain controller (PDC emulator)"),
}


def windows_label(sysd):
    cap = sysd.get("os_caption") or sysd.get("product_name") or ""
    return re.sub(r"^Microsoft\s+", "", cap).strip()


def windows_release(sysd):
    return BUILDS.get(str(sysd.get("current_build") or ""), "")


def build_label(sysd):
    b, ubr = sysd.get("current_build"), sysd.get("ubr")
    if not b:
        return sysd.get("os_version") or ""
    return f"{b}.{ubr}" if ubr not in (None, "") else str(b)


def install_type(sysd, lang):
    t = (sysd.get("installation_type") or "").strip()
    if t == "Server Core":
        return "Server Core"
    if t == "Server":
        return tr(lang, "Skrivbordsmiljö", "Desktop Experience")
    return t


def platform(sysd, lang):
    m = f"{sysd.get('manufacturer') or ''} {sysd.get('model') or ''}".lower()
    if "virtual machine" in m and "microsoft" in m:
        return "Hyper-V"
    if "vmware" in m:
        return "VMware"
    if any(k in m for k in ("qemu", "kvm", "ovirt", "proxmox", "red hat", "nutanix", "openstack")):
        return "KVM"
    if "xen" in m:
        return "Xen"
    if "amazon ec2" in m:
        return "AWS EC2"
    if "google compute" in m:
        return "Google Cloud"
    return tr(lang, "Fysisk", "Physical")


def domain_role(sysd, lang):
    r = DOMAIN_ROLES.get(sysd.get("domain_role"))
    return tr(lang, *r) if r else ""


# =============================================================================
# Roller och funktioner
# =============================================================================

# Installerade på en ny Windows Server utan att någon har lagt till dem. Gäller 2016 till 2025.
# FS-SMB1 (standard i 2016) räknas med flit inte hit, eftersom den bör synas i dokumentationen.
DEFAULT_FEATURES = {
    "FileAndStorage-Services", "Storage-Services",
    "NET-Framework-45-Features", "NET-Framework-45-Core", "NET-WCF-Services45", "NET-WCF-TCP-PortSharing45",
    "PowerShellRoot", "PowerShell", "PowerShell-V2", "PowerShell-ISE",
    "System-DataArchiver", "Windows-Defender", "Windows-Defender-Features", "Windows-Defender-Gui",
    "WoW64-Support", "XPS-Viewer", "Microsoft-Windows-Subsystem-Linux-Kernel",
}


def feature_rows(raw, lang):
    out = []
    for f in lst(raw.get("features")):
        if not isinstance(f, dict):
            continue
        name = f.get("name") or ""
        ftype = f.get("type") or "Feature"
        out.append({
            "name": name,
            "display_name": f.get("display_name") or name,
            "type": ftype,
            "type_label": {"Role": tr(lang, "Roll", "Role"),
                           "Role Service": tr(lang, "Rolltjänst", "Role service"),
                           "Feature": tr(lang, "Funktion", "Feature")}.get(ftype, ftype),
            "parent": f.get("parent") or "",
            "depth": int(f.get("depth") or 1),
            "default": name in DEFAULT_FEATURES,
        })
    return out


def added_roles(features):
    """Tillagda roller för översikten. En rolltjänst tas med när dess roll är standard, till exempel
    File Server under File and Storage Services, eftersom rollen själv då inte säger något."""
    by_name = {f["name"]: f for f in features}

    def root(f):
        seen = set()
        while f.get("parent") and f["parent"] in by_name and f["name"] not in seen:
            seen.add(f["name"])
            f = by_name[f["parent"]]
        return f

    out = []
    for f in features:
        if f["default"]:
            continue
        if f["type"] == "Role":
            out.append(f["display_name"])
        elif f["type"] == "Role Service":
            r = root(f)
            if r["type"] == "Role" and r["default"]:
                out.append(f["display_name"])
    return out


def added_features(features):
    return [f["display_name"] for f in features
            if f["type"] == "Feature" and not f["default"] and f["depth"] <= 1]


# =============================================================================
# Tjänster: vilka är utöver Windows standard?
# =============================================================================
# En tjänst räknas som Windows standard när programfilen ligger under Windows-katalogen och
# Microsoft är tillverkare, eller när den är en av de få Microsoft-tjänster som följer med
# Windows men ligger utanför Windows-katalogen (Defender, Edge). Instanser av användartjänster
# (till exempel CDPUserSvc_4a1b2) skapas av Windows för varje inloggad användare och räknas också
# som standard. Allt annat redovisas: tredjepart och Microsoft-produkter som installerats i
# efterhand, till exempel SQL Server.

WINDOWS_EXTRA_PATHS = (
    r"\program files\windows defender",
    r"\programdata\microsoft\windows defender",
    r"\program files\windows defender advanced threat protection",
    r"\program files\microsoft update health tools",
    r"\program files\common files\microsoft shared\clicktorun",  # Microsoft 365, men bara via Microsoft
)
WINDOWS_EXTRA_NAMES = {
    "edgeupdate", "edgeupdatem", "microsoftedgeelevationservice", "mdcoresvc", "windefend", "wdnissvc", "sense",
}
USER_INSTANCE = re.compile(r"_[0-9a-f]{4,8}$", re.I)

SERVICE_CLASSES = {
    "windows": ("Windows standard", "Windows default"),
    "microsoft": ("Microsoft, tillagd", "Microsoft, added"),
    "thirdparty": ("Tredjepart", "Third party"),
}


def is_microsoft(company):
    return "microsoft" in (company or "").lower()


def classify_service(s):
    name = (s.get("name") or "").lower()
    exe = (s.get("exe") or s.get("path") or "").lower().replace("/", "\\")
    company = s.get("company") or ""
    if USER_INSTANCE.search(name) and "svchost" in exe:
        return "windows"
    if name in WINDOWS_EXTRA_NAMES and (is_microsoft(company) or not company):
        return "windows"
    in_windows = bool(re.search(r"^(?:[a-z]:)?\\windows\\", exe)) or "\\systemroot\\" in exe
    in_extra = any(p in exe for p in WINDOWS_EXTRA_PATHS)
    if (in_windows or in_extra) and (is_microsoft(company) or not company):
        # Utan tillverkare (filen gick inte att läsa) räcker platsen under Windows-katalogen.
        return "windows"
    if is_microsoft(company):
        return "microsoft"
    return "thirdparty"


START_MODES = {
    "Auto": ("Automatisk", "Automatic"), "Manual": ("Manuell", "Manual"),
    "Disabled": ("Inaktiverad", "Disabled"), "Boot": ("Start", "Boot"), "System": ("System", "System"),
}
STATES = {
    "Running": ("Körs", "Running"), "Stopped": ("Stoppad", "Stopped"), "Paused": ("Pausad", "Paused"),
    "Start Pending": ("Startar", "Start pending"), "Stop Pending": ("Stoppar", "Stop pending"),
}


def service_rows(raw, lang, hidden=()):
    hidden = {h.lower() for h in hidden}
    out = []
    for s in lst(raw.get("services")):
        if not isinstance(s, dict):
            continue
        cls = classify_service(s)
        if cls != "windows" and (s.get("name") or "").lower() in hidden:
            cls = "hidden"
        start = START_MODES.get(s.get("start_mode") or "", (s.get("start_mode") or "",) * 2)
        start_l = tr(lang, *start)
        if s.get("delayed") and s.get("start_mode") == "Auto":
            start_l += tr(lang, " (fördröjd)", " (delayed)")
        st = STATES.get(s.get("state") or "", (s.get("state") or "",) * 2)
        out.append({
            "name": s.get("name") or "",
            "display_name": s.get("display_name") or s.get("name") or "",
            "class": cls,
            "class_label": tr(lang, "Dold av användaren", "Hidden by user") if cls == "hidden"
            else tr(lang, *SERVICE_CLASSES[cls]),
            "state": tr(lang, *st),
            "start": start_l,
            "account": s.get("account") or "",
            "company": s.get("company") or "",
            "product": s.get("product") or "",
            "version": s.get("file_version") or "",
            "path": s.get("path") or "",
            "description": s.get("description") or "",
        })
    out.sort(key=lambda r: r["display_name"].lower())
    return out


def extra_services(services):
    return [s for s in services if s["class"] in ("microsoft", "thirdparty")]


# =============================================================================
# En server som en samling tabeller
# =============================================================================

def network_rows(raw):
    out = []
    for n in lst(raw.get("network")):
        if not isinstance(n, dict):
            continue
        v4 = [f"{a.get('address')}/{prefix_of(a.get('mask'))}" for a in lst(n.get("ipv4")) if isinstance(a, dict)]
        v6 = [f"{a.get('address')}/{prefix_of(a.get('mask'))}" for a in lst(n.get("ipv6"))
              if isinstance(a, dict) and not str(a.get("address", "")).lower().startswith("fe80")]
        out.append({
            "name": n.get("name") or n.get("description") or "",
            "description": n.get("description") or "",
            "ipv4": v4,
            "ipv6": v6,
            "gateways": [str(g) for g in lst(n.get("gateways"))],
            "dns_servers": [str(d) for d in lst(n.get("dns_servers"))],
            "dns_suffix": n.get("dns_suffix") or "",
            "dhcp": bool(n.get("dhcp")),
            "mac": n.get("mac") or "",
            "register_dns": bool(n.get("register_dns")),
        })
    return out


def disk_rows(raw):
    out = []
    for d in lst(raw.get("disks")):
        if not isinstance(d, dict):
            continue
        size, free = d.get("size_bytes") or 0, d.get("free_bytes") or 0
        out.append({
            "drive": d.get("drive") or "", "label": d.get("label") or "", "fs": d.get("file_system") or "",
            "size_gib": gib(size), "free_gib": gib(free),
            "free_pct": round(100.0 * free / size, 0) if size else None,
        })
    return out


def software_rows(raw):
    out = []
    for s in lst(raw.get("software")):
        if not isinstance(s, dict) or not s.get("name"):
            continue
        d = str(s.get("install_date") or "")
        if re.fullmatch(r"\d{8}", d):
            d = f"{d[:4]}-{d[4:6]}-{d[6:]}"
        out.append({"name": s["name"], "version": s.get("version") or "", "publisher": s.get("publisher") or "",
                    "install_date": d, "arch": s.get("arch") or ""})
    out.sort(key=lambda r: r["name"].lower())
    return out


def share_rows(raw):
    return [{"name": s.get("name") or "", "path": s.get("path") or "", "description": s.get("description") or ""}
            for s in lst(raw.get("shares")) if isinstance(s, dict)]


def firewall_label(raw, lang):
    fw = [f for f in lst(raw.get("firewall")) if isinstance(f, dict)]
    if not fw:
        return ""
    on = [f["profile"] for f in fw if f.get("enabled")]
    off = [f["profile"] for f in fw if not f.get("enabled")]
    if not off:
        return tr(lang, "På för alla profiler", "On for all profiles")
    if not on:
        return tr(lang, "Av för alla profiler", "Off for all profiles")
    return tr(lang, f"På: {', '.join(on)}. Av: {', '.join(off)}", f"On: {', '.join(on)}. Off: {', '.join(off)}")


def yes_no(v, lang):
    if v is None:
        return ""
    return tr(lang, "Ja", "Yes") if v else tr(lang, "Nej", "No")


def build_server(raw, lang="sv", note=None, hidden=()):
    """Allt om en server, färdigt för Excel, Word och webben."""
    note = note or {}
    sysd = raw.get("system") or {}
    meta = raw.get("_meta") or {}
    feats = feature_rows(raw, lang)
    svcs = service_rows(raw, lang, hidden)
    nets = network_rows(raw)
    upd = raw.get("updates") or {}
    cpu = sysd.get("cpu_name") or ""
    if sysd.get("cpu_cores"):
        sockets = sysd.get("cpu_sockets") or 1
        cpu_short = tr(lang, f"{sockets} {'sockel' if sockets == 1 else 'socklar'}, {sysd.get('cpu_cores')} kärnor, "
                             f"{sysd.get('logical_cpus')} logiska",
                       f"{sockets} {'socket' if sockets == 1 else 'sockets'}, {sysd.get('cpu_cores')} cores, "
                       f"{sysd.get('logical_cpus')} logical")
    else:
        cpu_short = ""
    ipv4 = [ip for n in nets for ip in n["ipv4"]]
    dns_servers = []
    for n in nets:
        for d in n["dns_servers"]:
            if d not in dns_servers:
                dns_servers.append(d)
    rel = windows_release(sysd)
    return {
        "name": server_name(raw),
        "fqdn": sysd.get("fqdn") or "",
        "domain": sysd.get("domain") or "",
        "part_of_domain": bool(sysd.get("part_of_domain")),
        "domain_role": domain_role(sysd, lang),
        "is_dc": sysd.get("domain_role") in (4, 5),
        "windows": windows_label(sysd),
        "release": rel,
        "build": build_label(sysd),
        "display_version": sysd.get("display_version") or "",
        "install_type": install_type(sysd, lang),
        "install_date": date_only(sysd.get("install_date")),
        "last_boot": datetime_short(sysd.get("last_boot")),
        "platform": platform(sysd, lang),
        "manufacturer": sysd.get("manufacturer") or "",
        "model": sysd.get("model") or "",
        "serial": sysd.get("serial_number") or "",
        "bios": sysd.get("bios_version") or "",
        "cpu": cpu,
        "cpu_short": cpu_short,
        "logical_cpus": sysd.get("logical_cpus"),
        "memory_gib": gib(sysd.get("memory_bytes")),
        "time_zone": sysd.get("time_zone") or "",
        "rdp": yes_no(sysd.get("rdp_enabled"), lang),
        "firewall": firewall_label(raw, lang),
        "os_description": sysd.get("description") or "",
        "ipv4": ipv4,
        "dns_servers": dns_servers,
        "dns_primary_suffix": (raw.get("dns") or {}).get("primary_suffix") or "",
        "dns_search_list": [str(x) for x in lst((raw.get("dns") or {}).get("search_list"))],
        "network": nets,
        "disks": disk_rows(raw),
        "features": feats,
        "features_source": raw.get("features_source") or "",
        "roles_added": added_roles(feats),
        "features_added": added_features(feats),
        "services": svcs,
        "services_extra": extra_services(svcs),
        "software": software_rows(raw),
        "shares": share_rows(raw),
        "last_update": date_only(upd.get("last_installed")),
        "last_update_id": upd.get("last_id") or "",
        "update_count": upd.get("count") or 0,
        "description": (note.get("description") or "").strip(),
        "owner": (note.get("owner") or "").strip(),
        "meta": {
            "method": meta.get("method") or "",
            "collected_by": meta.get("collected_by") or "",
            "collected_from": meta.get("collected_from") or "",
            "collected": datetime_short(meta.get("collected_local") or meta.get("collected_utc")),
            "collected_utc": meta.get("collected_utc") or "",
            "collector_version": meta.get("collector_version") or "",
            "elevated": meta.get("elevated"),
            "ps_version": meta.get("ps_version") or "",
        },
        "errors": [e for e in lst(raw.get("_errors")) if isinstance(e, dict)],
    }


def server_summary(s, lang):
    """En rad i serverlistan i webben."""
    return {
        "name": s["name"], "fqdn": s["fqdn"], "ip": ", ".join(i.split("/")[0] for i in s["ipv4"]),
        "windows": s["windows"], "build": s["build"], "roles": s["roles_added"],
        "extra_services": len(s["services_extra"]), "collected": s["meta"]["collected"],
        "description": s["description"], "domain_role": s["domain_role"], "is_dc": s["is_dc"], "platform": s["platform"],
        "errors": len(s["errors"]), "elevated": s["meta"]["elevated"],
    }


def sort_servers(servers):
    return sorted(servers, key=lambda s: s["name"])


# =============================================================================
# Iakttagelser
# =============================================================================
# Enkla, sakliga kontroller som går att göra utifrån underlaget. Nivå: crit, warn eller info.

# Slutdatum för Microsofts utökade support (Extended Support), enligt Microsoft Lifecycle.
SUPPORT_END = {"2012 R2": "2023-10-10", "2016": "2027-01-12", "2019": "2029-01-09", "2022": "2031-10-14",
               "2025": "2034-10-10"}
DISK_WARN_PCT = 15
DISK_CRIT_PCT = 5
UPDATE_WARN_DAYS = 60


def observations(s, lang, today=None):
    import datetime as dt
    today = today or dt.date.today()
    out = []

    def add(level, text):
        out.append({"server": s["name"], "level": level, "text": text})

    end = SUPPORT_END.get(s["release"])
    if end:
        d = dt.date.fromisoformat(end)
        if d < today:
            add("crit", tr(lang, f"Windows Server {s['release']} saknar support från Microsoft sedan {end}.",
                           f"Windows Server {s['release']} has been out of Microsoft support since {end}."))
        elif (d - today).days < 365:
            add("warn", tr(lang, f"Supporten för Windows Server {s['release']} upphör {end}.",
                           f"Support for Windows Server {s['release']} ends {end}."))
    if any(f["name"] == "FS-SMB1" for f in s["features"]):
        add("warn", tr(lang, "SMB 1.0 är installerat. Protokollet är föråldrat och bör tas bort.",
                       "SMB 1.0 is installed. The protocol is outdated and should be removed."))
    if s["firewall"] and not s["firewall"].startswith(tr(lang, "På för alla", "On for all")):
        add("warn", tr(lang, f"Windows-brandväggen är inte på för alla profiler ({s['firewall']}).",
                       f"Windows Firewall is not on for all profiles ({s['firewall']})."))
    for d in s["disks"]:
        p = d["free_pct"]
        if p is None:
            continue
        if p < DISK_CRIT_PCT:
            add("crit", tr(lang, f"Volym {d['drive']} har bara {fnum(p, lang, 0)} % ledigt.",
                           f"Volume {d['drive']} has only {fnum(p, lang, 0)} % free."))
        elif p < DISK_WARN_PCT:
            add("warn", tr(lang, f"Volym {d['drive']} har {fnum(p, lang, 0)} % ledigt.",
                           f"Volume {d['drive']} has {fnum(p, lang, 0)} % free."))
    if s["last_update"]:
        try:
            ref = dt.date.fromisoformat((s["meta"]["collected"] or str(today))[:10])
            age = (ref - dt.date.fromisoformat(s["last_update"])).days
            if age > UPDATE_WARN_DAYS:
                add("warn", tr(lang, f"Senaste uppdateringen installerades för {age} dagar sedan ({s['last_update']}).",
                               f"The latest update was installed {age} days ago ({s['last_update']})."))
        except ValueError:
            pass
    if s["meta"]["elevated"] is False:
        add("info", tr(lang, "Insamlingen gjordes utan administratörsrätt. Roller och tjänster kan saknas.",
                       "Collected without administrator rights. Roles and services may be missing."))
    if s["errors"]:
        add("info", tr(lang, f"Insamlingen hade {len(s['errors'])} fel, se bilagan.",
                       f"The collection had {len(s['errors'])} errors, see the appendix."))
    return out
