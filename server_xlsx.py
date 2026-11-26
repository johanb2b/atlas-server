#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Excel-filen i Atlas Server: en flik per område, en rad per server, nätverkskort, roll, tjänst och så vidare."""
from __future__ import annotations

import io

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

import server_model as m

HEAD_FILL = PatternFill("solid", fgColor="EEF2F5")
HEAD_FONT = Font(bold=True)


def sheets(servers, lang="sv"):
    """Flikarna som (namn, kolumner, rader). Samma tabeller används av webben."""
    t = lambda sv, en: m.tr(lang, sv, en)  # noqa: E731
    servers = m.sort_servers(servers)
    out = []
    out.append((t("Servrar", "Servers"), [
        t("Server", "Server"), "FQDN", t("Domän", "Domain"), t("Domänroll", "Domain role"), t("IP-adresser", "IP addresses"),
        t("DNS-servrar", "DNS servers"), "Windows", t("Version", "Release"), "Build", t("Installationstyp", "Installation type"),
        t("Plattform", "Platform"), t("Tillverkare", "Manufacturer"), t("Modell", "Model"), t("Logiska CPU", "Logical CPUs"),
        t("Minne (GiB)", "Memory (GiB)"), t("Tillagda roller", "Added roles"), t("Tillagda funktioner", "Added features"),
        t("Tjänster utöver standard", "Services beyond defaults"), t("Senaste uppdatering", "Latest update"),
        t("Senaste omstart", "Last boot"), t("Beskrivning", "Description"), t("Ansvarig", "Owner"),
        t("Insamlat", "Collected"),
    ], [[
        s["name"], s["fqdn"], s["domain"], s["domain_role"], ", ".join(s["ipv4"]), ", ".join(s["dns_servers"]),
        s["windows"], s["release"], s["build"], s["install_type"], s["platform"], s["manufacturer"], s["model"],
        s["logical_cpus"], s["memory_gib"], ", ".join(s["roles_added"]), ", ".join(s["features_added"]), len(s["services_extra"]),
        s["last_update"], s["last_boot"], s["description"] or s["os_description"], s["owner"], s["meta"]["collected"],
    ] for s in servers]))

    out.append((t("Nätverk", "Network"), [
        t("Server", "Server"), t("Nätverkskort", "Adapter"), t("Beskrivning", "Description"), "IPv4", "IPv6", "Gateway",
        t("DNS-servrar", "DNS servers"), t("DNS-suffix", "DNS suffix"), "DHCP", t("Registrera i DNS", "Register in DNS"), "MAC",
    ], [[s["name"], n["name"], n["description"], ", ".join(n["ipv4"]), ", ".join(n["ipv6"]), ", ".join(n["gateways"]),
         ", ".join(n["dns_servers"]), n["dns_suffix"], m.yes_no(n["dhcp"], lang), m.yes_no(n["register_dns"], lang),
         n["mac"]] for s in servers for n in s["network"]]))

    out.append((t("Roller och funktioner", "Roles and features"), [
        t("Server", "Server"), t("Typ", "Type"), t("Namn", "Name"), t("Tekniskt namn", "Technical name"),
        t("Överordnad", "Parent"), t("Standard", "Default"),
    ], [[s["name"], f["type_label"], f["display_name"], f["name"], f["parent"], m.yes_no(f["default"], lang)]
        for s in servers for f in s["features"]]))

    svc_cols = [t("Server", "Server"), t("Tjänst", "Service"), t("Namn", "Name"), t("Klass", "Class"),
                t("Status", "Status"), t("Start", "Startup"), t("Konto", "Account"), t("Tillverkare", "Manufacturer"),
                t("Produkt", "Product"), "Version", t("Sökväg", "Path")]

    def svc_row(s, x):
        return [s["name"], x["display_name"], x["name"], x["class_label"], x["state"], x["start"], x["account"],
                x["company"], x["product"], x["version"], x["path"]]

    out.append((t("Tjänster utöver standard", "Extra services"), svc_cols,
                [svc_row(s, x) for s in servers for x in s["services_extra"]]))
    out.append((t("Alla tjänster", "All services"), svc_cols,
                [svc_row(s, x) for s in servers for x in s["services"]]))

    out.append((t("Program", "Software"), [
        t("Server", "Server"), t("Program", "Software"), "Version", t("Utgivare", "Publisher"),
        t("Installerat", "Installed"), t("Arkitektur", "Architecture"),
    ], [[s["name"], x["name"], x["version"], x["publisher"], x["install_date"], x["arch"]]
        for s in servers for x in s["software"]]))

    out.append((t("Diskar", "Disks"), [
        t("Server", "Server"), t("Volym", "Volume"), t("Etikett", "Label"), t("Filsystem", "File system"),
        t("Storlek (GiB)", "Size (GiB)"), t("Ledigt (GiB)", "Free (GiB)"), t("Ledigt (%)", "Free (%)"),
    ], [[s["name"], x["drive"], x["label"], x["fs"], x["size_gib"], x["free_gib"], x["free_pct"]]
        for s in servers for x in s["disks"]]))

    out.append((t("Utdelningar", "Shares"), [t("Server", "Server"), t("Namn", "Name"), t("Sökväg", "Path"),
                                             t("Beskrivning", "Description")],
                [[s["name"], x["name"], x["path"], x["description"]] for s in servers for x in s["shares"]]))

    obs = [o for s in servers for o in m.observations(s, lang)]
    out.append((t("Iakttagelser", "Observations"), [t("Server", "Server"), t("Nivå", "Level"),
                                                   t("Iakttagelse", "Observation")],
                [[o["server"], {"crit": t("Hög", "High"), "warn": t("Medel", "Medium"), "info": "Info"}[o["level"]],
                  o["text"]] for o in obs]))

    out.append((t("Insamling", "Collection"), [
        t("Server", "Server"), t("Insamlat", "Collected"), t("Metod", "Method"), t("Från", "From"),
        t("Konto", "Account"), t("Admin", "Admin"), t("Insamlarens version", "Collector version"),
        "PowerShell", t("Fel", "Errors"),
    ], [[s["name"], s["meta"]["collected"], s["meta"]["method"], s["meta"]["collected_from"],
         s["meta"]["collected_by"], m.yes_no(s["meta"]["elevated"], lang), s["meta"]["collector_version"],
         s["meta"]["ps_version"], "; ".join(f"{e.get('section')}: {e.get('message')}" for e in s["errors"])]
        for s in servers]))
    return out


def to_xlsx(servers, lang="sv"):
    wb = Workbook()
    wb.remove(wb.active)
    for name, cols, rows in sheets(servers, lang):
        ws = wb.create_sheet(name[:31])
        ws.append(cols)
        for c in ws[1]:
            c.fill, c.font = HEAD_FILL, HEAD_FONT
            c.alignment = Alignment(vertical="top")
        for r in rows:
            ws.append(["" if v is None else v for v in r])
        ws.freeze_panes = "B2"
        if rows:
            ws.auto_filter.ref = f"A1:{get_column_letter(len(cols))}{len(rows) + 1}"
        for ci, col in enumerate(cols, start=1):
            longest = max([len(str(col))] + [len(str(r[ci - 1] or "")) for r in rows[:500]])
            ws.column_dimensions[get_column_letter(ci)].width = min(60, max(9, longest + 2))
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
