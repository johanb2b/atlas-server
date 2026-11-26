# Atlas Server

Dokumentation av Windows Server-miljöer. Ett PowerShell-skript läser av servrarna, filerna importeras i webbgränssnittet och blir ett Word-dokument och en Excel-fil, på svenska eller engelska. Syskon till [Atlas](https://github.com/johanb2b/atlas), som dokumenterar virtualiseringsmiljöer, med samma utseende och samma Word-stil.

| Del | Vad |
|---|---|
| **Insamlare** | `collector/Collect-AtlasServer.cmd`: PowerShell-skript som bara läser. Körs på servern, eller från en adminserver mot många servrar över WinRM. En JSON-fil per server. |
| **Webb i Docker** | Miljöer per kund, import maskin för maskin (JSON eller zip), en sida per server, beskrivning och ansvarig, logotyper och export. |
| **Word** | Försättsblad med dokumentstyrning, översikt, iakttagelser, en sida per server och en bilaga om insamlingen. |
| **KeePass** | KeePass XML (2.x) med en post per server: titel med namn, FQDN och roll, IP som URL, roller och tjänster i anteckningarna. Importeras under Arkiv, Importera. |
| **Excel** | Servrar, nätverk, roller och funktioner, tilläggstjänster, alla tjänster, program, diskar, utdelningar, iakttagelser och insamling. |

Per server dokumenteras namn, FQDN, domän och domänroll, IP-adresser, gateway och DNS-servrar, Windows-version och build, installationstyp, plattform och hårdvara, Windows-roller och funktioner (tillagda markeras), tjänster utöver Windows standard, utdelningar, diskar och installerade program.

## Kom igång

**1. Starta webben**

```bash
git clone https://github.com/johanb2b/atlas-server.git
cd atlas-server
docker compose up -d --build
```

Öppna https://localhost:8090 och logga in som `admin` med lösenordet `admin`. Du får välja ett eget lösenord direkt. Certifikatet är självsignerat.

**2. Samla in**

Hämta insamlaren under **Insamlare** i webben (eller mappen `collector/`) och kör på en server:

```bat
Collect-AtlasServer.cmd
```

eller från en adminserver i domänen mot flera servrar:

```bat
Collect-AtlasServer.cmd -ComputerName SRV01,SRV02,SRV03
Collect-AtlasServer.cmd -ComputerListFile servrar.txt -AskCredential
```

Filerna hamnar i `output` bredvid skriptet.

**3. Importera och exportera**

Skapa en miljö, släpp JSON-filerna eller en zip av `output` på importytan och klicka på **Word-dokument** eller **Excel**.

## Utan webben

```bash
pip install -r requirements.txt
python atlas_server_cli.py build output/ --customer "Exempel AB" --environment Produktion
```

## Tjänster utöver standard

En tjänst räknas som Windows standard när programfilen ligger i Windows-katalogen och Microsoft är tillverkare, och för Microsoft Defender och Microsoft Edge. Övriga redovisas som *Microsoft, tillagd* (till exempel SQL Server) eller *Tredjepart*. Tjänster som finns på alla servrar hos en kund, till exempel en övervakningsagent, kan döljas i miljöns inställningar.

## Säkerhet

* Insamlaren gör bara läsande anrop och använder aldrig `Win32_Product`. Inget installeras på servrarna.
* Lösenord sparas aldrig. Webben kontaktar inte servrarna.
* Inloggning krävs alltid, och HTTPS är på som standard.

## Utveckling

```bash
python -m pyflakes *.py tests
python tests/smoke_test.py
```

Regler för AI-agenter står i [AGENTS.md](AGENTS.md) och planen i [PLAN.md](PLAN.md).

## Licens

MIT, Copyright (c) 2026 Johan Andersson. Se [LICENSE](LICENSE) och [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md).

Microsoft, Windows och Windows Server är varumärken som tillhör Microsoft Corporation. Atlas Server är ett fristående verktyg utan koppling till Microsoft.
