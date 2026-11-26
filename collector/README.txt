Atlas Server, insamlare
=======================

Bara läsande. Ingenting installeras och ingenting ändras på servrarna.
Ingen Python behövs, bara Windows PowerShell 5.1 som finns i Windows Server 2016 och senare.

En server
---------
Kopiera mappen till servern och dubbelklicka på Collect-AtlasServer.cmd, helst som administratör
(högerklicka, Kör som administratör). Filen hamnar i mappen output bredvid skriptet.

Flera servrar från en adminserver
---------------------------------
Kräver WinRM (PowerShell Remoting), som är på som standard i Windows Server, och ett konto
som är administratör på servrarna.

    Collect-AtlasServer.cmd -ComputerName SRV01,SRV02,SRV03
    Collect-AtlasServer.cmd -ComputerListFile servrar.txt
    Collect-AtlasServer.cmd -ComputerListFile servrar.txt -AskCredential
    Collect-AtlasServer.cmd -ComputerName SRV01 -UseSSL

servrar.txt har ett namn per rad. Rader som börjar med # hoppas över.

Importera
---------
Öppna miljön i Atlas Server och släpp JSON-filerna, eller en zip av mappen output, på importytan.

Vad som läses
-------------
Datornamn, FQDN, domän och domänroll, Windows-version och build, hårdvara, nätverkskort med IP,
gateway och DNS, Windows-roller och funktioner, alla tjänster med programfilens tillverkare,
installerade program (från registret, inte Win32_Product), diskar, utdelningar, senaste
uppdatering, fjärrskrivbord och brandväggsprofiler.
