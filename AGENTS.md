# Regler för AI-agenter i Atlas Server

Gäller för alla AI-verktyg som arbetar i repot. Läs den och `PLAN.md` innan du börjar. Står något här i konflikt med en uppgift: fråga Johan.

## Om projektet

Atlas Server dokumenterar kunders Windows Server-miljöer. Det är ett syskon till [Atlas](https://github.com/johanb2b/atlas), som dokumenterar virtualiseringsmiljöer, och lånar dess utseende, inloggning och Word-stil. Ägare är Johan Andersson, B2B IT-Partner AB.

## Arkitektur

* Flödet är alltid: **insamlare (PowerShell), JSON per server, modell, Word, Excel och webb.**
* Insamlaren (`collector/`) är det enda som körs på kundens servrar. Den skriver svaren med så lite tolkning som möjligt. Vad som är standard och vad som är tillagt avgörs i `server_model.py`, så att reglerna kan ändras utan ny insamling.
* Webben kontaktar aldrig servrarna. Insamling över nätet från containern är en senare fas, se `PLAN.md`.
* JSON-formatet har `_meta.tool = "Atlas Server"` och `_meta.format`. Formatet ändras bara efter Johans ok, och äldre filer ska fortsätta gå att läsa.

## Säkerhet

* **Insamlaren bara läser:** Get-CimInstance, Get-WindowsFeature, Get-ItemProperty och liknande. Inga Set-, Remove-, Install-, Enable- eller Disable-cmdlets (undantag: Remove-TypeData, som bara gäller den egna PowerShell-sessionen), och aldrig `Win32_Product` (kan starta en reparation av MSI-paket). Röktestet kontrollerar detta.
* **Lösenord sparas aldrig.** `-AskCredential` håller kontot i minnet.
* Insamlaren ska fungera i Windows PowerShell 5.1 och sparas som UTF-8 med BOM och CRLF.
* Kör aldrig nedladdade program i utvecklingsmiljön.

## Kunddata

* **Aldrig i Git:** `data/`, `output/`, insamlade JSON-filer från riktiga servrar, exporter och `.env`.
* Testdata i `tests/data/` skapas med `tests/make_examples.py`: Exempel AB, `exempel.local` och 10.10.10.0/24.

## Beroenden

* Samma bibliotek som Atlas: Flask, waitress och openpyxl. **Nytt bibliotek kräver Johans ok.** Word skrivs utan bibliotek.

## Texter och språk

* Allt användaren ser finns på svenska och engelska: `tr(lang, sv, en)` i Python, `data-en` i HTML och `L(sv, en)` i `app.js`.
* **Svenska utan tankstreck eller bindestreck som skiljetecken.** Bindestreck i sammansatta ord som Windows-brandväggen är ok.
* Dokumenten läses av kundens ledning och revisorer: sakligt, kort och utan säljspråk.

## Test

```bash
python -m pyflakes *.py tests
python tests/smoke_test.py
```

* En ny uppgift i insamlaren får ett fält i `tests/make_examples.py` och ett test i röktestet.
* Säg i pull requesten vad som inte har kunnat testas, till exempel mot en riktig Windows Server.

## Git

* En gren per uppgift och pull request mot `main`. Skriv vad som är nytt under `## [Unreleased]` i `CHANGELOG.md`.
* Bara Johan märker versioner och ger ut releaser.
