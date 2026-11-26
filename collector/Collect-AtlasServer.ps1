<#
.SYNOPSIS
    Atlas Server: samlar in dokumentationsunderlag från Windows Server. Bara läsande.

.DESCRIPTION
    Läser namn, nätverk, DNS, Windows-roller och funktioner, Windows-version, tjänster,
    installerade program, diskar, utdelningar och brandväggsprofiler, och skriver en JSON-fil
    per server. Filen importeras sedan i webbgränssnittet för Atlas Server.

    Utan parametrar samlas den egna datorn in. Med -ComputerName eller -ComputerListFile
    samlas andra servrar in över WinRM (PowerShell Remoting, Invoke-Command) med Kerberos
    som standard. Inget installeras och ingenting ändras på servrarna.

    Skriptet gör bara läsande anrop: Get-CimInstance, Get-WindowsFeature, Get-ItemProperty
    och liknande. Det anropar inte Win32_Product, eftersom den klassen kan starta en
    reparation av Windows Installer-paket.

.PARAMETER ComputerName
    En eller flera servrar att samla in över WinRM. Utelämna för att samla in den egna datorn.

.PARAMETER ComputerListFile
    Textfil med ett servernamn per rad. Tomma rader och rader som börjar med # hoppas över.

.PARAMETER OutputPath
    Katalog för JSON-filerna. Standard: mappen output bredvid skriptet.

.PARAMETER AskCredential
    Fråga efter ett annat konto för WinRM. Lösenordet hålls bara i minnet.

.PARAMETER UseSSL
    WinRM över HTTPS (port 5986) i stället för HTTP med Kerberos-kryptering (port 5985).

.EXAMPLE
    .\Collect-AtlasServer.cmd
    Samlar in den egna servern.

.EXAMPLE
    .\Collect-AtlasServer.cmd -ComputerName SRV01,SRV02
    Samlar in två servrar från en adminserver i domänen.

.EXAMPLE
    .\Collect-AtlasServer.cmd -ComputerListFile servrar.txt -AskCredential
#>
[CmdletBinding()]
param(
    [string[]]$ComputerName,
    [string]$ComputerListFile,
    [string]$OutputPath,
    [switch]$AskCredential,
    [switch]$UseSSL
)

$ErrorActionPreference = 'Stop'
$CollectorVersion = '1.0.0'

# -----------------------------------------------------------------------------
# Själva insamlingen. Körs på servern som dokumenteras, lokalt eller via
# Invoke-Command, och returnerar en JSON-sträng. Allt måste därför finnas inne i
# blocket, och varje avsnitt har en egen try/catch så att ett fel aldrig stoppar
# resten. Felen hamnar i _errors.
# -----------------------------------------------------------------------------
$Collect = {
    param($CollectorVersion, $Method, $CollectedFrom)

    $ErrorActionPreference = 'Stop'
    # Windows PowerShell 5.1 skriver annars listor som {"value": [...], "Count": n} i JSON.
    # Gäller bara den här PowerShell-sessionen, inget ändras på servern.
    Remove-TypeData System.Array -ErrorAction SilentlyContinue
    $errors = New-Object System.Collections.ArrayList

    function Add-Err($section, $err) {
        [void]$errors.Add([ordered]@{ section = $section; message = "$err" })
    }
    function Iso($d) {
        if ($null -eq $d -or "$d" -eq '') { return $null }
        try { return ([datetime]$d).ToString('s') } catch { return "$d" }
    }
    function Arr($x) {
        # Alltid en lista, även med ett eller inget värde, så att JSON blir [] och inte null eller en sträng.
        if ($null -eq $x) { return ,@() }
        return ,@($x | Where-Object { $null -ne $_ -and "$_" -ne '' } | ForEach-Object { "$_" })
    }

    $data = [ordered]@{}
    $data._meta = [ordered]@{
        tool              = 'Atlas Server'
        format            = 1
        collector_version = $CollectorVersion
        method            = $Method
        collected_from    = $CollectedFrom
        collected_by      = "$env:USERDOMAIN\$env:USERNAME"
        collected_utc     = (Get-Date).ToUniversalTime().ToString('s') + 'Z'
        collected_local   = (Get-Date).ToString('s')
        ps_version        = "$($PSVersionTable.PSVersion)"
        elevated          = $false
    }
    try {
        $id = [Security.Principal.WindowsIdentity]::GetCurrent()
        $data._meta.elevated = (New-Object Security.Principal.WindowsPrincipal $id).IsInRole(
            [Security.Principal.WindowsBuiltInRole]::Administrator)
    } catch { Add-Err 'meta' $_ }

    # --- System och Windows-version ------------------------------------------
    $sys = [ordered]@{}
    try {
        $cs = Get-CimInstance Win32_ComputerSystem
        $os = Get-CimInstance Win32_OperatingSystem
        $sys.computer_name   = $env:COMPUTERNAME
        $sys.dns_hostname    = $cs.DNSHostName
        $sys.domain          = $cs.Domain
        $sys.part_of_domain  = [bool]$cs.PartOfDomain
        $sys.domain_role     = [int]$cs.DomainRole
        $sys.fqdn            = if ($cs.PartOfDomain) { "$($cs.DNSHostName).$($cs.Domain)" } else { $cs.DNSHostName }
        $sys.manufacturer    = $cs.Manufacturer
        $sys.model           = $cs.Model
        $sys.memory_bytes    = [int64]$cs.TotalPhysicalMemory
        $sys.logical_cpus    = [int]$cs.NumberOfLogicalProcessors
        $sys.hypervisor_present = [bool]$cs.HypervisorPresent
        $sys.os_caption      = $os.Caption
        $sys.os_version      = $os.Version
        $sys.os_architecture = $os.OSArchitecture
        $sys.os_language     = [int]$os.OSLanguage
        $sys.description     = $os.Description
        $sys.install_date    = Iso $os.InstallDate
        $sys.last_boot       = Iso $os.LastBootUpTime
        $sys.registered_org  = $os.Organization
    } catch { Add-Err 'system' $_ }
    try {
        $cv = Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion'
        $sys.product_name      = $cv.ProductName
        $sys.edition_id        = $cv.EditionID
        $sys.installation_type = $cv.InstallationType
        $sys.display_version   = $cv.DisplayVersion
        $sys.current_build     = $cv.CurrentBuild
        $sys.ubr               = $cv.UBR
    } catch { Add-Err 'system.version' $_ }
    try {
        $bios = Get-CimInstance Win32_BIOS
        $sys.serial_number = $bios.SerialNumber
        $sys.bios_version  = $bios.SMBIOSBIOSVersion
    } catch { Add-Err 'system.bios' $_ }
    try {
        $cpus = @(Get-CimInstance Win32_Processor)
        $sys.cpu_name    = ($cpus | Select-Object -First 1).Name
        $sys.cpu_sockets = $cpus.Count
        $sys.cpu_cores   = [int](($cpus | Measure-Object -Property NumberOfCores -Sum).Sum)
    } catch { Add-Err 'system.cpu' $_ }
    try { $sys.time_zone = (Get-CimInstance Win32_TimeZone).Caption } catch { Add-Err 'system.timezone' $_ }
    try {
        $ts = Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\Terminal Server' -Name fDenyTSConnections
        $sys.rdp_enabled = ($ts.fDenyTSConnections -eq 0)
    } catch { Add-Err 'system.rdp' $_ }
    $data.system = $sys

    # --- Nätverk och DNS ------------------------------------------------------
    $nics = New-Object System.Collections.ArrayList
    try {
        $names = @{}
        foreach ($a in @(Get-CimInstance Win32_NetworkAdapter)) { $names["$($a.Index)"] = $a.NetConnectionID }
        foreach ($c in @(Get-CimInstance Win32_NetworkAdapterConfiguration -Filter 'IPEnabled = TRUE')) {
            $v4 = New-Object System.Collections.ArrayList
            $v6 = New-Object System.Collections.ArrayList
            $ips = @($c.IPAddress); $masks = @($c.IPSubnet)
            for ($i = 0; $i -lt $ips.Count; $i++) {
                $m = if ($i -lt $masks.Count) { "$($masks[$i])" } else { '' }
                $entry = [ordered]@{ address = "$($ips[$i])"; mask = $m }
                if ("$($ips[$i])" -like '*:*') { [void]$v6.Add($entry) } else { [void]$v4.Add($entry) }
            }
            [void]$nics.Add([ordered]@{
                index           = [int]$c.Index
                name            = $names["$($c.Index)"]
                description     = $c.Description
                mac             = $c.MACAddress
                dhcp            = [bool]$c.DHCPEnabled
                ipv4            = @($v4)
                ipv6            = @($v6)
                gateways        = Arr $c.DefaultIPGateway
                dns_servers     = Arr $c.DNSServerSearchOrder
                dns_suffix      = $c.DNSDomain
                register_dns    = [bool]$c.FullDNSRegistrationEnabled
            })
        }
    } catch { Add-Err 'network' $_ }
    $data.network = @($nics)

    $dns = [ordered]@{}
    try {
        $tcp = Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters'
        $dns.primary_suffix = $tcp.Domain
        $dns.search_list    = Arr ("$($tcp.SearchList)" -split ',')
    } catch { Add-Err 'dns' $_ }
    $data.dns = $dns

    # --- Windows-roller och funktioner ---------------------------------------
    $feat = New-Object System.Collections.ArrayList
    $data.features_source = $null
    try {
        if (Get-Command Get-WindowsFeature -ErrorAction SilentlyContinue) {
            foreach ($f in @(Get-WindowsFeature | Where-Object { $_.Installed })) {
                [void]$feat.Add([ordered]@{
                    name = $f.Name; display_name = $f.DisplayName; type = "$($f.FeatureType)"
                    parent = $f.Parent; depth = [int]$f.Depth
                })
            }
            $data.features_source = 'Get-WindowsFeature'
        } elseif (Get-Command Get-WindowsOptionalFeature -ErrorAction SilentlyContinue) {
            foreach ($f in @(Get-WindowsOptionalFeature -Online | Where-Object { "$($_.State)" -eq 'Enabled' })) {
                [void]$feat.Add([ordered]@{
                    name = $f.FeatureName; display_name = $f.FeatureName; type = 'Feature'; parent = $null; depth = 1
                })
            }
            $data.features_source = 'Get-WindowsOptionalFeature'
        }
    } catch { Add-Err 'features' $_ }
    $data.features = @($feat)

    # --- Tjänster ------------------------------------------------------------
    # Allt samlas in. Vilka som räknas som Windows standard avgörs när dokumentet byggs,
    # med hjälp av sökvägen och tillverkaren i programfilen.
    function Get-ExePath($p) {
        if (-not $p) { return $null }
        $p = "$p".Trim()
        $x = $null
        if ($p.StartsWith('"')) {
            $end = $p.IndexOf('"', 1)
            if ($end -gt 1) { $x = $p.Substring(1, $end - 1) }
        } elseif ($p -match '^(.+?\.(exe|sys|dll|com))(\s|$)') {
            $x = $matches[1]
        } else {
            $x = ($p -split '\s+')[0]
        }
        if (-not $x) { return $null }
        $x = [Environment]::ExpandEnvironmentVariables($x)
        if ($x.StartsWith('\??\')) { $x = $x.Substring(4) }
        if ($x -like '\SystemRoot\*') { $x = $env:SystemRoot + $x.Substring(11) }
        if ($x -match '^(?i)system32\\') { $x = Join-Path $env:SystemRoot $x }
        return $x
    }
    $svc = New-Object System.Collections.ArrayList
    try {
        $cache = @{}
        foreach ($s in @(Get-CimInstance Win32_Service)) {
            $exe = Get-ExePath $s.PathName
            $company = $null; $product = $null; $fver = $null
            if ($exe) {
                if (-not $cache.ContainsKey($exe)) {
                    $vi = $null
                    try { $vi = (Get-Item -LiteralPath $exe -ErrorAction Stop).VersionInfo } catch { }
                    $cache[$exe] = $vi
                }
                $vi = $cache[$exe]
                if ($vi) { $company = $vi.CompanyName; $product = $vi.ProductName; $fver = $vi.FileVersion }
            }
            [void]$svc.Add([ordered]@{
                name = $s.Name; display_name = $s.DisplayName; state = "$($s.State)"
                start_mode = "$($s.StartMode)"; delayed = [bool]$s.DelayedAutoStart
                account = $s.StartName; path = $s.PathName; exe = $exe
                company = $company; product = $product; file_version = $fver
                service_type = "$($s.ServiceType)"; description = $s.Description
            })
        }
    } catch { Add-Err 'services' $_ }
    $data.services = @($svc)

    # --- Installerade program (från registret, inte Win32_Product) -----------
    $sw = New-Object System.Collections.ArrayList
    try {
        $keys = @(
            @{ p = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*'; a = 'x64' },
            @{ p = 'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*'; a = 'x86' }
        )
        $seen = @{}
        foreach ($k in $keys) {
            foreach ($r in @(Get-ItemProperty $k.p -ErrorAction SilentlyContinue)) {
                if (-not $r.DisplayName -or $r.SystemComponent -eq 1 -or $r.ParentKeyName) { continue }
                $key = "$($r.DisplayName)|$($r.DisplayVersion)"
                if ($seen.ContainsKey($key)) { continue }
                $seen[$key] = $true
                [void]$sw.Add([ordered]@{
                    name = $r.DisplayName; version = $r.DisplayVersion; publisher = $r.Publisher
                    install_date = $r.InstallDate; arch = $k.a
                })
            }
        }
    } catch { Add-Err 'software' $_ }
    $data.software = @($sw)

    # --- Diskar ----------------------------------------------------------------
    $vols = New-Object System.Collections.ArrayList
    try {
        foreach ($d in @(Get-CimInstance Win32_LogicalDisk -Filter 'DriveType = 3')) {
            [void]$vols.Add([ordered]@{
                drive = $d.DeviceID; label = $d.VolumeName; file_system = $d.FileSystem
                size_bytes = [int64]$d.Size; free_bytes = [int64]$d.FreeSpace
            })
        }
    } catch { Add-Err 'disks' $_ }
    $data.disks = @($vols)

    # --- Utdelningar (utan de administrativa med $) ---------------------------
    $shares = New-Object System.Collections.ArrayList
    try {
        foreach ($s in @(Get-CimInstance Win32_Share)) {
            if ("$($s.Name)".EndsWith('$')) { continue }
            [void]$shares.Add([ordered]@{ name = $s.Name; path = $s.Path; description = $s.Description })
        }
    } catch { Add-Err 'shares' $_ }
    $data.shares = @($shares)

    # --- Uppdateringar ---------------------------------------------------------
    $upd = [ordered]@{ count = 0; last_installed = $null; last_id = $null }
    try {
        $q = @(Get-CimInstance Win32_QuickFixEngineering)
        $upd.count = $q.Count
        $dated = @($q | ForEach-Object {
            $when = $null
            try { $when = [datetime]::Parse("$($_.InstalledOn)", [Globalization.CultureInfo]::InvariantCulture) } catch { }
            if ($when) { [pscustomobject]@{ id = $_.HotFixID; when = $when } }
        } | Sort-Object when -Descending)
        if ($dated.Count -gt 0) { $upd.last_installed = Iso $dated[0].when; $upd.last_id = $dated[0].id }
    } catch { Add-Err 'updates' $_ }
    $data.updates = $upd

    # --- Brandvägg -------------------------------------------------------------
    $fw = New-Object System.Collections.ArrayList
    try {
        if (Get-Command Get-NetFirewallProfile -ErrorAction SilentlyContinue) {
            foreach ($p in @(Get-NetFirewallProfile)) {
                [void]$fw.Add([ordered]@{ profile = "$($p.Name)"; enabled = ("$($p.Enabled)" -eq 'True') })
            }
        }
    } catch { Add-Err 'firewall' $_ }
    $data.firewall = @($fw)

    $data._errors = @($errors)
    return ($data | ConvertTo-Json -Depth 8 -Compress)
}

# -----------------------------------------------------------------------------
# Huvudprogram
# -----------------------------------------------------------------------------
function Write-Utf8([string]$Path, [string]$Text) {
    [IO.File]::WriteAllText($Path, $Text, (New-Object Text.UTF8Encoding $false))
}

function Save-Result([string]$Name, [string]$Json) {
    $safe = ($Name -replace '[^A-Za-z0-9._-]', '_')
    $file = Join-Path $OutputPath ("atlasserver_{0}_{1}.json" -f $safe, (Get-Date -Format 'yyyyMMdd-HHmmss'))
    Write-Utf8 $file $Json
    return $file
}

if (-not $OutputPath) { $OutputPath = Join-Path $PSScriptRoot 'output' }
if (-not (Test-Path -LiteralPath $OutputPath)) { New-Item -ItemType Directory -Path $OutputPath | Out-Null }
$OutputPath = (Resolve-Path -LiteralPath $OutputPath).Path

$targets = @()
# Med powershell -File kommer SRV01,SRV02 som en enda sträng, så den delas här.
if ($ComputerName) { $targets += @($ComputerName | ForEach-Object { "$_" -split '[,;\s]+' } | Where-Object { $_ }) }
if ($ComputerListFile) {
    $targets += @(Get-Content -LiteralPath $ComputerListFile | ForEach-Object { $_.Trim() } |
                  Where-Object { $_ -and -not $_.StartsWith('#') })
}
$targets = @($targets | Select-Object -Unique)

Write-Host "Atlas Server insamlare $CollectorVersion (bara läsande)"
Write-Host "Utdata: $OutputPath"

if ($targets.Count -eq 0) {
    Write-Host "Samlar in den här datorn: $env:COMPUTERNAME"
    $json = & $Collect $CollectorVersion 'local' $env:COMPUTERNAME
    $file = Save-Result $env:COMPUTERNAME $json
    Write-Host "Klart: $file" -ForegroundColor Green
    $parsed = $json | ConvertFrom-Json
    if (-not $parsed._meta.elevated) {
        Write-Warning 'Skriptet kördes utan administratörsrätt. Roller och vissa tjänster kan saknas. Kör igen som administratör för fullständigt underlag.'
    }
    exit 0
}

$cred = $null
if ($AskCredential) { $cred = Get-Credential -Message 'Konto för WinRM mot servrarna (sparas inte)' }

$failed = 0
foreach ($t in $targets) {
    Write-Host "Samlar in $t ..." -NoNewline
    $params = @{
        ComputerName = $t
        ScriptBlock  = $Collect
        ArgumentList = @($CollectorVersion, 'remote', $env:COMPUTERNAME)
        ErrorAction  = 'Stop'
    }
    if ($cred) { $params.Credential = $cred }
    if ($UseSSL) { $params.UseSSL = $true }
    try {
        $json = Invoke-Command @params
        $name = ($json | ConvertFrom-Json).system.computer_name
        if (-not $name) { $name = $t }
        $file = Save-Result $name $json
        Write-Host " klart: $(Split-Path -Leaf $file)" -ForegroundColor Green
    } catch {
        $failed++
        Write-Host ' misslyckades' -ForegroundColor Red
        Write-Warning ("{0}: {1}. Kontrollera att WinRM är på (Enable-PSRemoting), att brandväggen släpper port 5985 och att kontot är administratör på servern." -f $t, $_.Exception.Message)
    }
}
Write-Host ("Klart. {0} av {1} servrar insamlade." -f ($targets.Count - $failed), $targets.Count)
if ($failed -gt 0) { exit 1 } else { exit 0 }
