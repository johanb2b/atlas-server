# Ändringslogg

## [Unreleased]

### Nytt

* Export till KeePass XML (2.x): en grupp per miljö och en post per server. Titel är namn, FQDN och roll, URL är IP-adressen, anteckningarna har Windows, nätverk, roller och tjänster, och ikonen är server (3). Samma server får samma UUID, så en ny import uppdaterar posten. Knappen KeePass i miljön, eller `--keepass` på kommandoraden.
* Första versionen av Atlas Server, dokumentation av Windows Server-miljöer.
* Insamlare i PowerShell (`collector/Collect-AtlasServer.ps1` och `.cmd`) som bara läser. Körs lokalt på en server, eller från en adminserver mot en lista servrar över WinRM. Skriver en JSON-fil per server.
* Insamlar namn, FQDN, domän och domänroll, nätverkskort med IP, gateway och DNS, Windows-version och build, roller och funktioner, alla tjänster med tillverkare, installerade program, diskar, utdelningar, senaste uppdatering och brandväggsprofiler.
* Tjänster klassas som Windows standard, Microsoft tillagd eller tredjepart. Tjänster kan döljas per miljö.
* Webbgränssnitt i Docker med miljöer, import av JSON eller zip, serversidor, beskrivning och ansvarig per server, kundens och partnerns logotyp.
* Word-dokument i samma stil som Atlas, på svenska eller engelska, med försättsblad, översikt, iakttagelser, en sida per server och bilaga om insamlingen.
* Excel med tio flikar.
* Kommandoraden `atlas_server_cli.py build` bygger Word och Excel utan webben.
