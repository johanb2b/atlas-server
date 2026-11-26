#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Export till KeePass XML (2.x), för import i KeePass under Arkiv, Importera, KeePass XML (2.x).

En grupp per miljö och en post per server:
    Titel:     DC01: dc01.exempel.local Domänkontrollant och DNS
    URL:       serverns första IPv4-adress
    Anteckningar: Windows, domänroll, IP och DNS, roller, tjänster utöver standard och beskrivning
    Ikon:      3 (NetworkServer i KeePass standardikoner)

Användarnamn och lösenord lämnas tomma. Atlas Server känner inga lösenord.

UUID för grupp och poster räknas fram ur miljöns och serverns namn. Samma server får därför samma
UUID vid nästa export, och KeePass uppdaterar posten i stället för att skapa en dubblett när filen
importeras igen (KeePass jämför UUID och behåller den nyaste ändringen).
"""
from __future__ import annotations

import base64
import datetime as dt
import uuid
from xml.sax.saxutils import escape

import server_model as m

ICON_SERVER = 3     # NetworkServer
ICON_FOLDER = 48    # Folder
NAMESPACE = uuid.UUID("6f1c3a52-9d4e-4b1a-8a7e-3c5d2b1e0f47")


def kp_uuid(*parts):
    return base64.b64encode(uuid.uuid5(NAMESPACE, "\x1f".join(p.lower() for p in parts)).bytes).decode()


def xe(v):
    return escape("" if v is None else str(v), {'"': "&quot;"})


def role_label(s, lang):
    """Rollen i titeln: beskrivningen från webben, annars tillagda roller, annars domänrollen."""
    if s["description"]:
        return s["description"]
    if s["roles_added"]:
        return ", ".join(s["roles_added"])
    return s["domain_role"]


def title(s, lang):
    fqdn = (s["fqdn"] or s["name"]).lower()
    return " ".join(x for x in (f"{s['name']}:", fqdn, role_label(s, lang)) if x)


def first_ip(s):
    return s["ipv4"][0].split("/")[0] if s["ipv4"] else ""


def notes(s, lang):
    t = lambda sv, en: m.tr(lang, sv, en)  # noqa: E731
    lines = []

    def add(label, value):
        if value:
            lines.append(f"{label}: {value}")

    add(t("Beskrivning", "Description"), s["description"])
    add(t("Ansvarig", "Owner"), s["owner"])
    add("FQDN", s["fqdn"])
    add(t("Domänroll", "Domain role"), s["domain_role"])
    add("Windows", f"{s['windows']} ({s['build']})" if s["build"] else s["windows"])
    add(t("Installationstyp", "Installation type"), s["install_type"])
    add(t("Plattform", "Platform"), s["platform"])
    add(t("IP-adresser", "IP addresses"), ", ".join(s["ipv4"]))
    add(t("DNS-servrar", "DNS servers"), ", ".join(s["dns_servers"]))
    gws = [g for n in s["network"] for g in n["gateways"]]
    add("Gateway", ", ".join(dict.fromkeys(gws)))
    lines.append("")
    lines.append(t("Roller:", "Roles:"))
    lines += [f"  {r}" for r in s["roles_added"]] or [t("  Inga tillagda", "  None added")]
    if s["features_added"]:
        lines.append(t("Funktioner:", "Features:"))
        lines += [f"  {f}" for f in s["features_added"]]
    lines.append(t("Tjänster utöver standard:", "Services beyond the defaults:"))
    lines += [f"  {x['display_name']} ({x['name']})" for x in s["services_extra"]] or [t("  Inga", "  None")]
    if s["shares"]:
        lines.append(t("Utdelningar:", "Shares:"))
        lines += [f"  {x['name']}: {x['path']}" for x in s["shares"]]
    lines.append("")
    lines.append(t(f"Insamlat {s['meta']['collected']} med Atlas Server.",
                   f"Collected {s['meta']['collected']} with Atlas Server."))
    return "\n".join(lines)


def tags(s):
    out = ["Atlas Server"]
    if s["is_dc"]:
        out.append("DC")
    if s["release"]:
        out.append(f"WS{s['release'].replace(' ', '')}")
    return ";".join(out)


def times(now):
    return (f"<Times><CreationTime>{now}</CreationTime><LastModificationTime>{now}</LastModificationTime>"
            f"<LastAccessTime>{now}</LastAccessTime><ExpiryTime>{now}</ExpiryTime><Expires>False</Expires>"
            f"<UsageCount>0</UsageCount><LocationChanged>{now}</LocationChanged></Times>")


def string(key, value, protect=False):
    attr = ' ProtectInMemory="True"' if protect else ""
    return f"<String><Key>{key}</Key><Value{attr}>{xe(value)}</Value></String>"


def to_keepass_xml(servers, lang="sv", group_name="", env_id=""):
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    group_name = group_name or "Atlas Server"
    key = env_id or group_name
    entries = []
    for s in m.sort_servers(servers):
        entries.append(
            f"<Entry><UUID>{kp_uuid(key, s['name'])}</UUID><IconID>{ICON_SERVER}</IconID>"
            f"<ForegroundColor /><BackgroundColor /><OverrideURL /><Tags>{xe(tags(s))}</Tags>{times(now)}"
            + string("Title", title(s, lang)) + string("UserName", "") + string("Password", "", protect=True)
            + string("URL", first_ip(s)) + string("Notes", notes(s, lang))
            + "<AutoType><Enabled>True</Enabled><DataTransferObfuscation>0</DataTransferObfuscation></AutoType>"
            "<History /></Entry>")
    return ('<?xml version="1.0" encoding="utf-8" standalone="yes"?>\n'
            "<KeePassFile><Meta><Generator>Atlas Server</Generator></Meta><Root>"
            f"<Group><UUID>{kp_uuid(key)}</UUID><Name>{xe(group_name)}</Name><Notes /><IconID>{ICON_FOLDER}</IconID>"
            f"{times(now)}<IsExpanded>True</IsExpanded>{''.join(entries)}</Group>"
            "</Root></KeePassFile>\n").encode("utf-8")
