# Plan: Atlas Server

Mål: dokumentera Windows Server-miljöer på samma sätt som Atlas dokumenterar virtualiseringsmiljöer, med Word och Excel som resultat.

## Beslut

| Datum | Beslut |
|---|---|
| 2026-11-26 | Namnet är Atlas Server. Eget repo, inte en plattform i Atlas. |
| 2026-11-26 | Insamlingen görs med ett PowerShell-skript som bara läser, lokalt eller från en adminserver över WinRM. Ingen Python på servrarna. |
| 2026-11-26 | Webben i Docker importerar filerna. Insamling över nätet direkt från containern blir en senare fas. |

## Fas 1: Första versionen (Claude, klar 2026-11-26)

- [x] Insamlare i PowerShell, lokalt och mot en lista servrar över WinRM.
- [x] Modell med klassning av tjänster och roller, iakttagelser.
- [x] Word i Atlas stil och Excel med tio flikar, svenska och engelska.
- [x] Webbgränssnitt i Docker: miljöer, import av JSON och zip, serversidor, beskrivning, logotyper, export.
- [x] Kommandoraden `atlas_server_cli.py build`.
- [x] Röktest med påhittade exempelfiler.

### Antaganden i fas 1

Gjorda utan att fråga. Ändra gärna.

* **Standardtjänster:** en tjänst är Windows standard när programfilen ligger i Windows-katalogen och Microsoft är tillverkare, eller är Defender eller Edge. Roller som DNS och AD DS har sina tjänster i Windows-katalogen och syns därför under roller, inte bland tilläggstjänsterna.
* **Standardroller och funktioner** står i `DEFAULT_FEATURES` i `server_model.py`, efter vad en ny installation av 2016 till 2025 brukar ha. SMB 1.0 räknas med flit inte som standard.
* **Miljöer:** en miljö per kund eller del av en kund. Samma servernamn i en miljö ersätts av den nyaste insamlingen.
* **Port 8090** i Docker, så att Atlas på 8080 kan köras på samma värd.
* **Iakttagelser:** support från Microsoft, SMB 1.0, brandvägg av, lite ledigt diskutrymme, gamla uppdateringar och insamling utan administratörsrätt.

## Fas 2: Kontroll mot riktiga servrar (Johan, sedan Claude)

- [ ] Kör insamlaren lokalt på en ny Windows Server 2022 eller 2025 och importera filen.
- [ ] Kör insamlaren från en adminserver mot två eller tre servrar.
- [ ] Gå igenom listan över tilläggstjänster: finns något som borde räknas som standard, eller tvärtom? Justera `classify_service` och `DEFAULT_FEATURES`.
- [ ] Anonymisera en riktig fil och lägg den i `tests/data/`. Ett anonymiseringsverktyg som i Atlas behövs först.

## Fas 3: Windows-paket (Claude)

- [ ] Webben som Windows-paket utan Docker, byggt av GitHub som i Atlas (python.exe från python.org, bara ren Python).

## Fas 4: Insamling över nätet från webben (fråga Johan först)

Skriv in ett servernamn i webben och hämta uppgifterna direkt. Kräver WinRM från Linux och därmed nya bibliotek (pywinrm med NTLM eller Kerberos), som inte är ren Python. Alternativ som inte kräver nya beroenden:

* Windows-paketet (fas 3) anropar insamlaren med `Invoke-Command` via PowerShell, på samma sätt som Hyper V i Atlas.
* En liten agent på en adminserver som kör insamlaren och skickar filerna till webben.

## Att bekräfta med Johan

* Fler uppgifter i dokumentet? Till exempel lokala administratörer, schemalagda aktiviteter, lyssnande portar, certifikat eller IIS-webbplatser.
