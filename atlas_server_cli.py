#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Kommandoraden i Atlas Server: bygg Word och Excel direkt från filerna från insamlaren, utan webben.

    python atlas_server_cli.py build output/ --customer "Exempel AB" --environment Produktion
    python atlas_server_cli.py build a.json b.json --lang en --out dokumentation
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import server_docx
import server_keepass
import server_model as model
import server_xlsx


def collect_files(paths):
    files = []
    for p in map(Path, paths):
        if p.is_dir():
            files += sorted(p.glob("*.json"))
        elif p.is_file():
            files.append(p)
        else:
            sys.exit(f"FEL: hittar inte {p}")
    return files


def main(argv=None):
    ap = argparse.ArgumentParser(prog="atlas_server_cli.py", description="Atlas Server på kommandoraden.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="Bygg Word och Excel från filer eller mappar från insamlaren")
    b.add_argument("paths", nargs="+", help="JSON-filer eller mappar med JSON-filer")
    b.add_argument("--lang", choices=model.LANGS, default="sv")
    b.add_argument("--customer", default="")
    b.add_argument("--environment", default="")
    b.add_argument("--version", default="1.0")
    b.add_argument("--classification", choices=list(server_docx.CLASSIFICATIONS), default="internal")
    b.add_argument("--no-software", action="store_true", help="Utelämna installerade program i Word")
    b.add_argument("--keepass", action="store_true", help="Skriv även KeePass XML (2.x) för import i KeePass")
    b.add_argument("--out", default="", help="Filnamn utan ändelse. Standard: kund_serverdokumentation")
    a = ap.parse_args(argv)

    latest = {}
    for f in collect_files(a.paths):
        try:
            raw = model.load_raw(f)
        except model.FormatError as e:
            print(f"Hoppar över {f.name}: {e}", file=sys.stderr)
            continue
        name = model.server_name(raw)
        if name not in latest or raw["_meta"].get("collected_utc", "") > latest[name]["_meta"].get("collected_utc", ""):
            latest[name] = raw
    if not latest:
        sys.exit("FEL: inga giltiga filer från insamlaren.")
    servers = [model.build_server(r, a.lang) for r in latest.values()]
    info = server_docx.default_info(a.lang, customer=a.customer, system=a.environment, version=a.version,
                                    classification=a.classification)
    stem = a.out or server_docx.file_name(a.customer or a.environment, "x", a.lang)[:-2]
    Path(f"{stem}.docx").write_bytes(server_docx.to_docx(
        server_docx.build_doc(servers, a.lang, info, show_software=not a.no_software)))
    Path(f"{stem}.xlsx").write_bytes(server_xlsx.to_xlsx(servers, a.lang))
    written = [f"{stem}.docx", f"{stem}.xlsx"]
    if a.keepass:
        group = ", ".join(x for x in (a.customer, a.environment) if x)
        Path(f"{stem}_keepass.xml").write_bytes(server_keepass.to_keepass_xml(servers, a.lang, group))
        written.append(f"{stem}_keepass.xml")
    print(f"{len(servers)} servrar. Skrev {', '.join(written)}")


if __name__ == "__main__":
    main()
