#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Word-dokumentet i Atlas Server: serverdokumentation för en Windows Server-miljö.

Word-filen skrivs direkt som Office Open XML, utan extra bibliotek, med samma utseende
som dokumenten från Atlas (Calibri, grön accent, försättsblad med dokumentstyrning,
sidhuvud och sidfot med sidnummer).

Dokumentet byggs först som en lista med block (rubrik, stycke, tabell och så vidare) och
skrivs sedan till docx. Samma block kan senare ge HTML eller Markdown.
"""
from __future__ import annotations

import datetime as dt
import io
import re
import struct
import zipfile
from xml.sax.saxutils import escape as _xesc

import server_model as m

PRODUCT = "Atlas Server"
CLASSIFICATIONS = {
    "internal": ("Intern", "Internal"),
    "confidential": ("Konfidentiell", "Confidential"),
    "restricted": ("Begränsad", "Restricted"),
    "public": ("Öppen", "Public"),
}
LEVELS = {
    "crit": ("Hög", "High", "F6C6C2"),
    "warn": ("Medel", "Medium", "FBE7B5"),
    "info": ("Info", "Info", "E3E7EB"),
}


# =============================================================================
# Dokumentet som block
# =============================================================================

class Doc:
    def __init__(self, lang, info):
        self.lang = lang
        self.info = info
        self.blocks = []

    def t(self, sv, en):
        return m.tr(self.lang, sv, en)

    def add(self, t, **kw):
        kw["t"] = t
        self.blocks.append(kw)

    def h1(self, text):
        self.add("h1", text=text)

    def h2(self, text):
        self.add("h2", text=text)

    def h3(self, text):
        self.add("h3", text=text)

    def p(self, text, cls=None):
        self.add("p", text=text, cls=cls)

    def kv(self, pairs):
        self.add("kv", pairs=[(k, v) for k, v in pairs if v not in (None, "")])

    def table(self, cols, rows, widths=None, empty=None, small=None, shade=None):
        self.add("table", cols=cols, rows=rows, widths=widths, small=small, shade=shade,
                 empty=empty or self.t("Inget att redovisa.", "Nothing to report."))


def join(v, sep=", "):
    return sep.join(str(x) for x in v if x not in (None, ""))


def default_info(lang="sv", **kw):
    today = dt.date.today().isoformat()
    info = {
        "title": m.tr(lang, "Serverdokumentation", "Server documentation"),
        "subtitle": m.tr(lang, "Windows Server-miljö", "Windows Server environment"),
        "customer": "", "system": "", "version": "1.0", "date": today, "classification": "internal",
        "owner": "", "approver": "",
        "partner": {"company": "", "consultant": "", "email": "", "phone": ""},
        "logos": {},
    }
    for k, v in kw.items():
        if k == "partner" and isinstance(v, dict):
            info["partner"].update({kk: vv for kk, vv in v.items() if kk in info["partner"]})
        elif v not in (None, ""):
            info[k] = v
    return info


def classification_label(c, lang):
    return m.tr(lang, *CLASSIFICATIONS.get(c, CLASSIFICATIONS["internal"]))


def build_doc(servers, lang="sv", info=None, show_software=True, show_all_features=True):
    """servers: lista från server_model.build_server. Returnerar ett Doc."""
    info = info or default_info(lang)
    d = Doc(lang, info)
    t = d.t
    servers = m.sort_servers(servers)
    obs = [o for s in servers for o in m.observations(s, lang)]
    collected = sorted(s["meta"]["collected"][:10] for s in servers if s["meta"]["collected"])

    d.add("toc")

    # --- 1 Inledning ---------------------------------------------------------
    d.h1(t("Inledning", "Introduction"))
    period = ""
    if collected:
        period = collected[0] if collected[0] == collected[-1] else f"{collected[0]} {t('till', 'to')} {collected[-1]}"
    d.p(t(f"Dokumentet beskriver {len(servers)} servrar med Windows Server"
          + (f" i miljön {info['system']}" if info.get("system") else "")
          + (f" hos {info['customer']}" if info.get("customer") else "") + ". "
          "Det redovisar namn, nätverk och DNS, Windows-version, installerade roller och funktioner, "
          "tjänster utöver Windows standard, diskar och installerade program.",
          f"This document describes {len(servers)} servers running Windows Server"
          + (f" in the {info['system']} environment" if info.get("system") else "")
          + (f" at {info['customer']}" if info.get("customer") else "") + ". "
          "It covers names, network and DNS, Windows version, installed roles and features, services beyond "
          "the Windows defaults, disks and installed software."), cls="lead")
    d.p(t(f"Underlaget samlades in med {PRODUCT}, som bara läser från servrarna"
          + (f", {period}" if period else "") + ". Uppgifterna gäller vid insamlingen och behöver hållas aktuella "
          "när miljön ändras.",
          f"The data was collected with {PRODUCT}, which only reads from the servers"
          + (f", {period}" if period else "") + ". The information is valid as of the collection and needs to be "
          "kept up to date when the environment changes."))

    # --- 2 Översikt ----------------------------------------------------------
    d.h1(t("Översikt", "Overview"))
    rels = {}
    for s in servers:
        key = s["windows"] or t("Okänd", "Unknown")
        rels[key] = rels.get(key, 0) + 1
    domains = sorted({s["domain"] for s in servers if s["domain"]})
    d.kv([
        (t("Antal servrar", "Number of servers"), str(len(servers))),
        (t("Domäner", "Domains"), join(domains)),
        (t("Domänkontrollanter", "Domain controllers"), join(s["name"] for s in servers if s["is_dc"]) or t("Inga", "None")),
        (t("Windows-versioner", "Windows versions"), join(f"{k} ({v})" for k, v in sorted(rels.items()))),
        (t("Insamlat", "Collected"), period),
    ])
    d.h2(t("Servrar", "Servers"))
    d.table([t("Server", "Server"), t("IP-adress", "IP address"), "Windows", t("Roller", "Roles"),
             t("Beskrivning", "Description")],
            [[s["name"], join(i.split("/")[0] for i in s["ipv4"]),
              f"{s['windows']} ({s['build']})" if s["build"] else s["windows"],
              join(s["roles_added"]) or t("Inga tillagda", "None added"), s["description"] or s["os_description"]] for s in servers],
            widths=[14, 16, 26, 26, 18], small=False)
    if obs:
        d.h2(t("Iakttagelser", "Observations"))
        d.p(t("Sådant i underlaget som kan behöva åtgärdas eller följas upp.",
              "Items in the data that may need action or follow-up."))
        order = {"crit": 0, "warn": 1, "info": 2}
        obs.sort(key=lambda o: (order[o["level"]], o["server"]))
        d.table([t("Server", "Server"), t("Nivå", "Level"), t("Iakttagelse", "Observation")],
                [[o["server"], t(*LEVELS[o["level"]][:2]), o["text"]] for o in obs], widths=[16, 12, 72],
                small=False, shade=[{1: LEVELS[o["level"]][2]} for o in obs])

    # --- 3 Servrar -----------------------------------------------------------
    d.add("pagebreak")
    d.h1(t("Servrar", "Servers"))
    for n, s in enumerate(servers):
        if n:
            d.add("pagebreak")
        d.h2(s["name"])
        if s["description"]:
            d.p(s["description"], cls="lead")
        d.h3(t("Grunduppgifter", "General"))
        d.kv([
            (t("Datornamn", "Computer name"), s["name"]),
            ("FQDN", s["fqdn"]),
            (t("Domän", "Domain"), s["domain"]),
            (t("Domänroll", "Domain role"), s["domain_role"]),
            (t("Ansvarig", "Owner"), s["owner"]),
            ("Windows", s["windows"]),
            (t("Version och build", "Version and build"),
             join([s["display_version"], s["build"]], ", build ") if s["display_version"] else s["build"]),
            (t("Installationstyp", "Installation type"), s["install_type"]),
            (t("Installerad", "Installed"), s["install_date"]),
            (t("Senaste omstart", "Last boot"), s["last_boot"]),
            (t("Senaste uppdatering", "Latest update"), join([s["last_update"], s["last_update_id"]], ", ")),
            (t("Plattform", "Platform"), s["platform"]),
            (t("Tillverkare och modell", "Manufacturer and model"), join([s["manufacturer"], s["model"]])),
            (t("Serienummer", "Serial number"), s["serial"]),
            ("CPU", join([s["cpu"], s["cpu_short"]], ", ")),
            (t("Minne", "Memory"), f"{m.fnum(s['memory_gib'], lang)} GiB" if s["memory_gib"] else ""),
            (t("Tidszon", "Time zone"), s["time_zone"]),
            (t("Fjärrskrivbord", "Remote Desktop"), s["rdp"]),
            (t("Windows-brandväggen", "Windows Firewall"), s["firewall"]),
            (t("Datorbeskrivning i Windows", "Computer description in Windows"),
             s["os_description"] if s["os_description"] != s["description"] else ""),
        ])

        d.h3(t("Nätverk och DNS", "Network and DNS"))
        d.table([t("Nätverkskort", "Adapter"), t("IP-adress", "IP address"), "Gateway", t("DNS-servrar", "DNS servers"),
                 "DHCP", "MAC"],
                [[n["name"], join(n["ipv4"] + n["ipv6"], "\n"), join(n["gateways"], "\n"), join(n["dns_servers"], "\n"),
                  m.yes_no(n["dhcp"], lang), n["mac"]] for n in s["network"]],
                widths=[18, 22, 14, 18, 8, 20], small=False)
        d.kv([
            (t("Primärt DNS-suffix", "Primary DNS suffix"), s["dns_primary_suffix"]),
            (t("Sökordning för DNS-suffix", "DNS suffix search list"), join(s["dns_search_list"])),
        ])

        d.h3(t("Diskar", "Disks"))
        d.table([t("Volym", "Volume"), t("Etikett", "Label"), t("Filsystem", "File system"),
                 t("Storlek (GiB)", "Size (GiB)"), t("Ledigt (GiB)", "Free (GiB)"), t("Ledigt", "Free")],
                [[x["drive"], x["label"], x["fs"], m.fnum(x["size_gib"], lang), m.fnum(x["free_gib"], lang),
                  f"{m.fnum(x['free_pct'], lang, 0)} %" if x["free_pct"] is not None else ""] for x in s["disks"]],
                widths=[12, 22, 14, 18, 18, 16], small=False)

        d.h3(t("Windows-roller och funktioner", "Windows roles and features"))
        feats = s["features"] if show_all_features else [f for f in s["features"] if not f["default"]]
        if s["features_source"] == "" and not feats:
            d.p(t("Roller och funktioner kunde inte läsas på servern.",
                  "Roles and features could not be read on the server."), cls="note")
        else:
            d.table([t("Namn", "Name"), t("Typ", "Type"), t("Tekniskt namn", "Technical name"), t("Tillagd", "Added")],
                    [["   " * max(0, f["depth"] - 1) + f["display_name"], f["type_label"], f["name"],
                      t("Standard", "Default") if f["default"] else t("Ja", "Yes")] for f in feats],
                    widths=[44, 16, 28, 12], small=False)
            if show_all_features:
                d.p(t("Standard betyder att rollen eller funktionen följer med en ny installation av Windows Server.",
                      "Default means that the role or feature comes with a new installation of Windows Server."),
                    cls="note")

        d.h3(t("Tjänster utöver Windows standard", "Services beyond the Windows defaults"))
        d.table([t("Tjänst", "Service"), t("Namn", "Name"), t("Start", "Startup"), t("Status", "Status"),
                 t("Konto", "Account"), t("Tillverkare", "Manufacturer")],
                [[x["display_name"], x["name"], x["start"], x["state"], x["account"], x["company"]]
                 for x in s["services_extra"]], widths=[30, 16, 13, 10, 17, 14],
                empty=t("Inga tjänster utöver Windows standard.", "No services beyond the Windows defaults."))

        if s["shares"]:
            d.h3(t("Utdelningar", "Shares"))
            d.table([t("Namn", "Name"), t("Sökväg", "Path"), t("Beskrivning", "Description")],
                    [[x["name"], x["path"], x["description"]] for x in s["shares"]], widths=[22, 48, 30], small=False)

        if show_software:
            d.h3(t("Installerade program", "Installed software"))
            d.table([t("Program", "Software"), "Version", t("Utgivare", "Publisher"), t("Installerat", "Installed")],
                    [[x["name"], x["version"], x["publisher"], x["install_date"]] for x in s["software"]],
                    widths=[46, 16, 26, 12])

    # --- Bilaga --------------------------------------------------------------
    d.add("pagebreak")
    d.h1(t("Bilaga: Insamling", "Appendix: Collection"))
    d.p(t(f"Underlaget samlades in med insamlaren i {PRODUCT}, ett PowerShell-skript som bara gör läsande anrop "
          "(Get-CimInstance, Get-WindowsFeature och registret). Det kördes lokalt på servern eller från en "
          "adminserver över WinRM. Inget installerades och ingenting ändrades på servrarna.",
          f"The data was collected with the {PRODUCT} collector, a PowerShell script that only makes read calls "
          "(Get-CimInstance, Get-WindowsFeature and the registry). It ran locally on the server or from an "
          "admin server over WinRM. Nothing was installed and nothing was changed on the servers."))
    d.p(t("En tjänst räknas som Windows standard när programfilen ligger i Windows-katalogen och Microsoft är "
          "tillverkare, samt för Microsoft Defender och Microsoft Edge. Övriga tjänster redovisas, även "
          "Microsoft-produkter som installerats i efterhand, till exempel SQL Server.",
          "A service counts as a Windows default when its program file is in the Windows directory and Microsoft "
          "is the manufacturer, and for Microsoft Defender and Microsoft Edge. All other services are listed, "
          "including Microsoft products installed afterwards, such as SQL Server."), cls="note")
    d.table([t("Server", "Server"), t("Insamlat", "Collected"), t("Metod", "Method"), t("Konto", "Account"),
             t("Admin", "Admin"), t("Version", "Version"), t("Fel", "Errors")],
            [[s["name"], s["meta"]["collected"],
              {"local": t("Lokalt", "Local"), "remote": t("WinRM från ", "WinRM from ") + s["meta"]["collected_from"]}
              .get(s["meta"]["method"], s["meta"]["method"]),
              s["meta"]["collected_by"], m.yes_no(s["meta"]["elevated"], lang), s["meta"]["collector_version"],
              str(len(s["errors"]))] for s in servers], widths=[13, 17, 20, 22, 8, 10, 10], small=False)
    errs = [(s["name"], e) for s in servers for e in s["errors"]]
    if errs:
        d.h2(t("Fel vid insamlingen", "Collection errors"))
        d.table([t("Server", "Server"), t("Avsnitt", "Section"), t("Meddelande", "Message")],
                [[n, e.get("section") or "", e.get("message") or ""] for n, e in errs], widths=[15, 18, 67])
    return d


# =============================================================================
# Word (.docx), skrivs direkt som Office Open XML
# =============================================================================

W_NS = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"')
_XML_BAD = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
PAGE_W = 11906 - 2 * 1134


def xe(v):
    return _xesc(_XML_BAD.sub("", "" if v is None else str(v)))


def w_run(text, bold=False, color=None, size=None):
    props = ""
    if bold or color or size:
        props = "<w:rPr>" + ("<w:b/>" if bold else "") + (f'<w:color w:val="{color}"/>' if color else "") + \
                (f'<w:sz w:val="{size}"/><w:szCs w:val="{size}"/>' if size else "") + "</w:rPr>"
    parts = str(text if text is not None else "").split("\n")
    inner = "<w:br/>".join(f'<w:t xml:space="preserve">{xe(x)}</w:t>' for x in parts)
    return f"<w:r>{props}{inner}</w:r>"


def w_p(text="", style=None, bold=False, align=None, runs=None, keep_next=False, spacing=None):
    ppr = ""
    if style or align or keep_next or spacing:
        ppr = "<w:pPr>" + (f'<w:pStyle w:val="{style}"/>' if style else "") + \
              ("<w:keepNext/>" if keep_next else "") + (spacing or "") + \
              (f'<w:jc w:val="{align}"/>' if align else "") + "</w:pPr>"
    body = runs if runs is not None else (w_run(text, bold=bold) if text != "" else "")
    return f"<w:p>{ppr}{body}</w:p>"


def w_table(cols, rows, widths=None, small=True, shade=None, header=True, first_bold=False):
    n = len(cols)
    if widths and len(widths) == n:
        tw = sum(widths)
        ws = [int(PAGE_W * w / tw) for w in widths]
    else:
        ws = [int(PAGE_W / n)] * n
    style = "TableTextSmall" if small else "TableText"
    grid = "".join(f'<w:gridCol w:w="{w}"/>' for w in ws)
    out = [f'<w:tbl><w:tblPr><w:tblStyle w:val="AtlasTable"/><w:tblW w:w="5000" w:type="pct"/>'
           f'<w:tblLayout w:type="fixed"/><w:tblLook w:val="04A0" w:firstRow="1" w:lastRow="0" '
           f'w:firstColumn="0" w:lastColumn="0" w:noHBand="1" w:noVBand="1"/></w:tblPr><w:tblGrid>{grid}</w:tblGrid>']

    def tc(v, w, fill=None, bold=False):
        shd = f'<w:shd w:val="clear" w:color="auto" w:fill="{fill}"/>' if fill else ""
        return (f'<w:tc><w:tcPr><w:tcW w:w="{w}" w:type="dxa"/>{shd}</w:tcPr>'
                f'{w_p(style=style, runs=w_run(v, bold=bold))}</w:tc>')

    if header:
        out.append("<w:tr><w:trPr><w:tblHeader/><w:cantSplit/></w:trPr>" +
                   "".join(tc(c, ws[ci], fill="EEF2F5", bold=True) for ci, c in enumerate(cols)) + "</w:tr>")
    for ri, r in enumerate(rows):
        fills = shade[ri] if shade else {}
        out.append("<w:tr><w:trPr><w:cantSplit/></w:trPr>" +
                   "".join(tc(v, ws[ci], fill=fills.get(ci), bold=first_bold and ci == 0)
                           for ci, v in enumerate(r)) + "</w:tr>")
    out.append("</w:tbl>")
    out.append(w_p(style="Spacer"))
    return "".join(out)


def image_size(data):
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return struct.unpack(">II", data[16:24])
    if data[:2] == b"\xff\xd8":
        i = 2
        while i < len(data) - 9:
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            seglen = struct.unpack(">H", data[i + 2:i + 4])[0]
            if marker in (0xC0, 0xC1, 0xC2):
                h, w = struct.unpack(">HH", data[i + 5:i + 9])
                return w, h
            i += 2 + seglen
    return None


def w_image(rid, w_px, h_px, max_w_in=2.6, max_h_in=0.9, pid=1, name="Logotyp", after=360):
    emu = 914400
    scale = min(max_w_in * emu / w_px, max_h_in * emu / h_px)
    cx, cy = int(w_px * scale), int(h_px * scale)
    return (f'<w:p><w:pPr><w:keepNext/><w:spacing w:after="{after}"/></w:pPr><w:r><w:drawing>'
            f'<wp:inline distT="0" distB="0" distL="0" distR="0"><wp:extent cx="{cx}" cy="{cy}"/>'
            f'<wp:docPr id="{pid}" name="{xe(name)}"/><wp:cNvGraphicFramePr>'
            f'<a:graphicFrameLocks noChangeAspect="1"/></wp:cNvGraphicFramePr><a:graphic>'
            f'<a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture"><pic:pic>'
            f'<pic:nvPicPr><pic:cNvPr id="{pid}" name="{xe(name)}"/><pic:cNvPicPr/></pic:nvPicPr>'
            f'<pic:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
            f'<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
            f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic></a:graphicData>'
            f'</a:graphic></wp:inline></w:drawing></w:r></w:p>')


DOCX_STYLES = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles {W_NS}>
<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:eastAsia="Calibri" w:cs="Calibri"/>
<w:sz w:val="21"/><w:szCs w:val="21"/><w:color w:val="1F2933"/><w:lang w:val="@LANG@"/></w:rPr></w:rPrDefault>
<w:pPrDefault><w:pPr><w:spacing w:after="120" w:line="264" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>
<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/></w:style>
<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:qFormat/>
<w:pPr><w:spacing w:before="0" w:after="120"/></w:pPr><w:rPr><w:b/><w:sz w:val="56"/><w:szCs w:val="56"/><w:color w:val="0F172A"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Subtitle"><w:name w:val="Subtitle"/><w:basedOn w:val="Normal"/><w:qFormat/>
<w:rPr><w:sz w:val="26"/><w:szCs w:val="26"/><w:color w:val="017A5E"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Customer"><w:name w:val="Customer"/><w:basedOn w:val="Normal"/>
<w:pPr><w:spacing w:before="240" w:after="480"/></w:pPr><w:rPr><w:sz w:val="36"/><w:szCs w:val="36"/><w:color w:val="334155"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="PartnerLabel"><w:name w:val="Partner Label"/><w:basedOn w:val="Normal"/>
<w:pPr><w:keepNext/><w:pBdr><w:top w:val="single" w:sz="12" w:space="8" w:color="01A982"/></w:pBdr><w:spacing w:before="480" w:after="80"/></w:pPr>
<w:rPr><w:b/><w:caps/><w:spacing w:val="10"/><w:sz w:val="15"/><w:szCs w:val="15"/><w:color w:val="64748B"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="PartnerLine"><w:name w:val="Partner Line"/><w:basedOn w:val="Normal"/>
<w:pPr><w:keepNext/><w:spacing w:after="0"/></w:pPr><w:rPr><w:sz w:val="19"/><w:szCs w:val="19"/><w:color w:val="475569"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/>
<w:pPr><w:keepNext/><w:keepLines/><w:pBdr><w:bottom w:val="single" w:sz="8" w:space="4" w:color="01A982"/></w:pBdr>
<w:spacing w:before="360" w:after="160"/><w:outlineLvl w:val="0"/></w:pPr><w:rPr><w:b/><w:sz w:val="32"/><w:szCs w:val="32"/><w:color w:val="0F172A"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/>
<w:pPr><w:keepNext/><w:keepLines/><w:spacing w:before="280" w:after="100"/><w:outlineLvl w:val="1"/></w:pPr><w:rPr><w:b/><w:sz w:val="25"/><w:szCs w:val="25"/><w:color w:val="017A5E"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading3"><w:name w:val="heading 3"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/>
<w:pPr><w:keepNext/><w:spacing w:before="200" w:after="80"/><w:outlineLvl w:val="2"/></w:pPr><w:rPr><w:b/><w:sz w:val="22"/><w:szCs w:val="22"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Lead"><w:name w:val="Lead"/><w:basedOn w:val="Normal"/><w:rPr><w:sz w:val="24"/><w:szCs w:val="24"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Note"><w:name w:val="Note"/><w:basedOn w:val="Normal"/><w:rPr><w:i/><w:sz w:val="18"/><w:szCs w:val="18"/><w:color w:val="5B6770"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="TableText"><w:name w:val="Table Text"/><w:basedOn w:val="Normal"/>
<w:pPr><w:spacing w:after="0" w:line="240" w:lineRule="auto"/></w:pPr><w:rPr><w:sz w:val="18"/><w:szCs w:val="18"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="TableTextSmall"><w:name w:val="Table Text Small"/><w:basedOn w:val="TableText"/>
<w:rPr><w:sz w:val="15"/><w:szCs w:val="15"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Spacer"><w:name w:val="Spacer"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:after="80"/></w:pPr><w:rPr><w:sz w:val="8"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Header"><w:name w:val="header"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:after="0"/></w:pPr><w:rPr><w:sz w:val="16"/><w:szCs w:val="16"/><w:color w:val="5B6770"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Footer"><w:name w:val="footer"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:after="0"/></w:pPr><w:rPr><w:sz w:val="16"/><w:szCs w:val="16"/><w:color w:val="5B6770"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="TOCHeading"><w:name w:val="TOC Heading"/><w:basedOn w:val="Heading1"/><w:pPr><w:outlineLvl w:val="9"/></w:pPr></w:style>
<w:style w:type="table" w:styleId="AtlasTable"><w:name w:val="Atlas Table"/><w:tblPr>
<w:tblBorders><w:top w:val="single" w:sz="4" w:space="0" w:color="C9D1D9"/><w:bottom w:val="single" w:sz="4" w:space="0" w:color="C9D1D9"/>
<w:insideH w:val="single" w:sz="4" w:space="0" w:color="E1E6EB"/></w:tblBorders>
<w:tblCellMar><w:top w:w="45" w:type="dxa"/><w:left w:w="85" w:type="dxa"/><w:bottom w:w="45" w:type="dxa"/><w:right w:w="85" w:type="dxa"/></w:tblCellMar></w:tblPr></w:style>
</w:styles>'''


def _logo_part(logo, stem):
    if not logo or not logo.get("data"):
        return None
    size = image_size(logo["data"])
    if not size or not all(size):
        return None
    ext = "png" if logo["data"][:4] == b"\x89PNG" else "jpeg"
    return (f"media/{stem}.{ext}", logo["data"], size)


def control_rows(d):
    i, t = d.info, d.t
    return [
        (t("Dokument", "Document"), i["title"]),
        (t("Kund", "Customer"), i["customer"] or t("Ej angiven", "Not set")),
        (t("Miljö", "Environment"), i["system"] or t("Ej angiven", "Not set")),
        ("Version", i["version"]),
        (t("Datum", "Date"), i["date"]),
        (t("Klassning", "Classification"), classification_label(i["classification"], d.lang)),
        (t("Dokumentägare", "Document owner"), i["owner"] or t("Anges av kunden", "Set by the customer")),
        (t("Godkänd av", "Approved by"), i["approver"] or t("Anges vid godkännande", "Set at approval")),
    ]


def to_docx(d):
    i, t = d.info, d.t
    cust = _logo_part(i["logos"].get("customer"), "customer")
    part = _logo_part(i["logos"].get("partner"), "partner")
    body = []
    if cust:
        body.append(w_image("rIdLogoC", *cust[2], pid=1, name=i["customer"] or "Logo", after=720))
    body.append(w_p(i["subtitle"], style="Subtitle"))
    body.append(w_p(i["title"], style="Title"))
    if i["customer"]:
        body.append(w_p(i["customer"], style="Customer"))
    body.append(w_table(["", ""], control_rows(d), widths=[30, 70], small=False, header=False, first_bold=True))
    p = i["partner"]
    if any(p.values()) or part:
        body.append(w_p(t("Upprättad av", "Prepared by"), style="PartnerLabel"))
        if part:
            body.append(w_image("rIdLogoP", *part[2], max_w_in=1.8, max_h_in=0.55, pid=2,
                                name=p["company"] or "Partner", after=120))
        if p["company"]:
            body.append(w_p(style="PartnerLine", runs=w_run(p["company"], bold=True, color="0F172A")))
        for x in (p["consultant"], p["email"], p["phone"]):
            if x:
                body.append(w_p(x, style="PartnerLine"))
    body.append(w_p(t(f"Skapat med {PRODUCT} {m.VERSION}.", f"Created with {PRODUCT} {m.VERSION}."), style="Note",
                    spacing='<w:spacing w:before="240"/>'))
    body.append('<w:p><w:r><w:br w:type="page"/></w:r></w:p>')

    for b in d.blocks:
        k = b["t"]
        if k == "toc":
            body.append(w_p(t("Innehåll", "Contents"), style="TOCHeading"))
            body.append('<w:p><w:r><w:fldChar w:fldCharType="begin"/></w:r><w:r><w:instrText xml:space="preserve">'
                        ' TOC \\o "1-2" \\h \\z \\u </w:instrText></w:r><w:r><w:fldChar w:fldCharType="separate"/>'
                        f'</w:r>{w_run(t("Högerklicka här och välj Uppdatera fält för att visa innehållsförteckningen.", "Right-click here and choose Update Field to show the table of contents."))}'
                        '<w:r><w:fldChar w:fldCharType="end"/></w:r></w:p>')
            body.append('<w:p><w:r><w:br w:type="page"/></w:r></w:p>')
        elif k in ("h1", "h2", "h3"):
            body.append(w_p(b["text"], style={"h1": "Heading1", "h2": "Heading2", "h3": "Heading3"}[k]))
        elif k == "p":
            body.append(w_p(b["text"], style={"lead": "Lead", "note": "Note"}.get(b.get("cls"))))
        elif k == "kv":
            if b["pairs"]:
                body.append(w_table(["", ""], b["pairs"], widths=[32, 68], small=False, header=False, first_bold=True))
        elif k == "table":
            if b["rows"]:
                small = b["small"] if b["small"] is not None else len(b["cols"]) > 5
                body.append(w_table(b["cols"], b["rows"], widths=b.get("widths"), small=small, shade=b.get("shade")))
            else:
                body.append(w_p(b["empty"], style="Note"))
        elif k == "pagebreak":
            body.append('<w:p><w:r><w:br w:type="page"/></w:r></w:p>')

    sect = ('<w:sectPr><w:headerReference w:type="default" r:id="rIdH1"/>'
            '<w:footerReference w:type="default" r:id="rIdF1"/><w:pgSz w:w="11906" w:h="16838"/>'
            '<w:pgMar w:top="1418" w:right="1134" w:bottom="1304" w:left="1134" w:header="624" w:footer="567" '
            'w:gutter="0"/><w:titlePg/></w:sectPr>')
    document = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                f'<w:document {W_NS} '
                'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
                'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
                'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">'
                f'<w:body>{"".join(body)}{sect}</w:body></w:document>')
    tab = f'<w:tabs><w:tab w:val="right" w:pos="{PAGE_W}"/></w:tabs>'
    head_text = i["title"] + (", " + i["customer"] if i["customer"] else "")
    header = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:hdr {W_NS}><w:p><w:pPr>'
              f'<w:pStyle w:val="Header"/>{tab}</w:pPr>{w_run(head_text)}'
              f'<w:r><w:tab/></w:r>{w_run(classification_label(i["classification"], d.lang), bold=True)}</w:p></w:hdr>')
    footer = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:ftr {W_NS}><w:p><w:pPr>'
              f'<w:pStyle w:val="Footer"/>{tab}</w:pPr>{w_run("Version " + i["version"] + ", " + i["date"])}'
              f'<w:r><w:tab/></w:r>{w_run(t("Sida ", "Page "))}'
              '<w:fldSimple w:instr=" PAGE "><w:r><w:t>1</w:t></w:r></w:fldSimple>'
              f'{w_run(t(" av ", " of "))}<w:fldSimple w:instr=" NUMPAGES "><w:r><w:t>1</w:t></w:r>'
              '</w:fldSimple></w:p></w:ftr>')
    settings = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:settings {W_NS}>'
                '<w:defaultTabStop w:val="709"/><w:characterSpacingControl w:val="doNotCompress"/>'
                '<w:compat><w:compatSetting w:name="compatibilityMode" w:uri="http://schemas.microsoft.com/office/word" '
                'w:val="15"/></w:compat></w:settings>')
    rel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    rels = [f'<Relationship Id="rIdS" Type="{rel}/styles" Target="styles.xml"/>',
            f'<Relationship Id="rIdT" Type="{rel}/settings" Target="settings.xml"/>',
            f'<Relationship Id="rIdH1" Type="{rel}/header" Target="header1.xml"/>',
            f'<Relationship Id="rIdF1" Type="{rel}/footer" Target="footer1.xml"/>']
    for rid, pd in (("rIdLogoC", cust), ("rIdLogoP", part)):
        if pd:
            rels.append(f'<Relationship Id="{rid}" Type="{rel}/image" Target="{pd[0]}"/>')
    doc_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                + "".join(rels) + "</Relationships>")
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    creator = ", ".join(x for x in (p["consultant"], p["company"]) if x) or PRODUCT
    core_xml = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
                'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
                'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
                f'<dc:title>{xe(head_text)}</dc:title><dc:creator>{xe(creator)}</dc:creator>'
                f'<dc:language>{"en-GB" if d.lang == "en" else "sv-SE"}</dc:language>'
                f'<cp:version>{xe(i["version"])}</cp:version>'
                f'<dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created>'
                f'<dcterms:modified xsi:type="dcterms:W3CDTF">{now}</dcterms:modified></cp:coreProperties>')
    app_xml = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
               '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">'
               f'<Application>{PRODUCT} {m.VERSION}</Application>'
               + (f'<Company>{xe(p["company"])}</Company>' if p["company"] else "") + '</Properties>')
    ct = "application/vnd.openxmlformats-officedocument"
    ctypes = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
              '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
              '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
              '<Default Extension="xml" ContentType="application/xml"/>'
              '<Default Extension="png" ContentType="image/png"/><Default Extension="jpeg" ContentType="image/jpeg"/>'
              f'<Override PartName="/word/document.xml" ContentType="{ct}.wordprocessingml.document.main+xml"/>'
              f'<Override PartName="/word/styles.xml" ContentType="{ct}.wordprocessingml.styles+xml"/>'
              f'<Override PartName="/word/settings.xml" ContentType="{ct}.wordprocessingml.settings+xml"/>'
              f'<Override PartName="/word/header1.xml" ContentType="{ct}.wordprocessingml.header+xml"/>'
              f'<Override PartName="/word/footer1.xml" ContentType="{ct}.wordprocessingml.footer+xml"/>'
              '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
              f'<Override PartName="/docProps/app.xml" ContentType="{ct}.extended-properties+xml"/>'
              '</Types>')
    root_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                 '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                 f'<Relationship Id="rId1" Type="{rel}/officeDocument" Target="word/document.xml"/>'
                 '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
                 f'<Relationship Id="rId3" Type="{rel}/extended-properties" Target="docProps/app.xml"/>'
                 '</Relationships>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", ctypes)
        z.writestr("_rels/.rels", root_rels)
        z.writestr("docProps/core.xml", core_xml)
        z.writestr("docProps/app.xml", app_xml)
        z.writestr("word/document.xml", document)
        z.writestr("word/styles.xml", DOCX_STYLES.replace("@LANG@", "en-GB" if d.lang == "en" else "sv-SE"))
        z.writestr("word/settings.xml", settings)
        z.writestr("word/header1.xml", header)
        z.writestr("word/footer1.xml", footer)
        z.writestr("word/_rels/document.xml.rels", doc_rels)
        for pd in (cust, part):
            if pd:
                z.writestr(f"word/{pd[0]}", pd[1])
    return buf.getvalue()


def file_name(customer, ext, lang="sv"):
    cust = re.sub(r"[^A-Za-z0-9åäöÅÄÖ._-]+", "-", str(customer or "")).strip("-") or m.tr(lang, "kund", "customer")
    return f"{cust}_{m.tr(lang, 'serverdokumentation', 'server-documentation')}.{ext}"
