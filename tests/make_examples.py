#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Skapar påhittade exempelfiler i samma format som insamlaren skriver (tests/data/*.json).

Exempel AB, domänen exempel.local och nätet 10.10.10.0/24. Inga riktiga namn eller adresser.
Kör om skriptet när formatet ändras: python tests/make_examples.py
"""
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent / "data"

WIN = r"C:\Windows\system32"


def svc(name, display, exe, company="Microsoft Corporation", state="Running", start="Auto", account="LocalSystem",
        product=None, path=None, delayed=False, desc=""):
    return {"name": name, "display_name": display, "state": state, "start_mode": start, "delayed": delayed,
            "account": account, "path": path or exe, "exe": exe, "company": company,
            "product": product or ("Microsoft® Windows® Operating System" if company and "Microsoft" in company
                                   else display),
            "file_version": "10.0.20348.1", "service_type": "Own Process", "description": desc}


BASE_SERVICES = [
    svc("Dhcp", "DHCP Client", WIN + r"\svchost.exe", path=WIN + r"\svchost.exe -k LocalServiceNetworkRestricted -p",
        account="NT Authority\\LocalService"),
    svc("Dnscache", "DNS Client", WIN + r"\svchost.exe", path=WIN + r"\svchost.exe -k NetworkService -p",
        account="NT AUTHORITY\\NetworkService"),
    svc("EventLog", "Windows Event Log", WIN + r"\svchost.exe", account="NT AUTHORITY\\LocalService"),
    svc("LanmanServer", "Server", WIN + r"\svchost.exe"),
    svc("LanmanWorkstation", "Workstation", WIN + r"\svchost.exe", account="NT AUTHORITY\\NetworkService"),
    svc("MpsSvc", "Windows Defender Firewall", WIN + r"\svchost.exe", account="NT Authority\\LocalService"),
    svc("TermService", "Remote Desktop Services", WIN + r"\svchost.exe", start="Manual",
        account="NT Authority\\NetworkService"),
    svc("W32Time", "Windows Time", WIN + r"\svchost.exe", account="NT AUTHORITY\\LocalService"),
    svc("WinRM", "Windows Remote Management (WS-Management)", WIN + r"\svchost.exe",
        account="NT AUTHORITY\\NetworkService"),
    svc("wuauserv", "Windows Update", WIN + r"\svchost.exe", start="Manual", state="Stopped"),
    svc("TrustedInstaller", "Windows Modules Installer", r"C:\Windows\servicing\TrustedInstaller.exe",
        start="Manual", state="Stopped"),
    svc("WinDefend", "Microsoft Defender Antivirus Service",
        r"C:\ProgramData\Microsoft\Windows Defender\Platform\4.18.25010.11-0\MsMpEng.exe"),
    svc("edgeupdate", "Microsoft Edge Update Service (edgeupdate)",
        r"C:\Program Files (x86)\Microsoft\EdgeUpdate\MicrosoftEdgeUpdate.exe", delayed=True),
    svc("CDPUserSvc_4a1b2", "Connected Devices Platform User Service_4a1b2", WIN + r"\svchost.exe",
        start="Auto", account=""),
    svc("Spooler", "Print Spooler", WIN + r"\spoolsv.exe"),
]


def features(*extra):
    base = [
        ("FileAndStorage-Services", "File and Storage Services", "Role", None, 1),
        ("Storage-Services", "Storage Services", "Role Service", "FileAndStorage-Services", 2),
        ("NET-Framework-45-Features", ".NET Framework 4.8 Features", "Feature", None, 1),
        ("NET-Framework-45-Core", ".NET Framework 4.8", "Feature", "NET-Framework-45-Features", 2),
        ("NET-WCF-Services45", "WCF Services", "Feature", "NET-Framework-45-Features", 2),
        ("NET-WCF-TCP-PortSharing45", "TCP Port Sharing", "Feature", "NET-WCF-Services45", 3),
        ("PowerShellRoot", "Windows PowerShell", "Feature", None, 1),
        ("PowerShell", "Windows PowerShell 5.1", "Feature", "PowerShellRoot", 2),
        ("System-DataArchiver", "System Data Archiver", "Feature", None, 1),
        ("Windows-Defender", "Microsoft Defender Antivirus", "Feature", None, 1),
        ("WoW64-Support", "WoW64 Support", "Feature", None, 1),
    ]
    rows = [{"name": n, "display_name": d, "type": t, "parent": p, "depth": dp} for n, d, t, p, dp in base]
    rows += [{"name": n, "display_name": d, "type": t, "parent": p, "depth": dp} for n, d, t, p, dp in extra]
    return rows


def base_software():
    return [
        {"name": "Microsoft Edge", "version": "131.0.2903.112", "publisher": "Microsoft Corporation",
         "install_date": "20250114", "arch": "x86"},
        {"name": "Microsoft Visual C++ 2015-2022 Redistributable (x64) - 14.40.33810", "version": "14.40.33810.0",
         "publisher": "Microsoft Corporation", "install_date": "20250114", "arch": "x86"},
    ]


def server(name, ip, build, ubr, caption, model, manufacturer, role, feats, services, software, shares=(),
           disks=None, description="", core=False, extra_nic=None, mem_gib=16, cores=4, rdp=True, errors=()):
    nics = [{
        "index": 1, "name": "Ethernet", "description": "Microsoft Hyper-V Network Adapter",
        "mac": "00-15-5D-0A-0A-%02X" % int(ip.split(".")[-1]), "dhcp": False,
        "ipv4": [{"address": ip, "mask": "255.255.255.0"}],
        "ipv6": [{"address": "fe80::1c2d:3e4f:5a6b:7c8d", "mask": "64"}],
        "gateways": ["10.10.10.1"], "dns_servers": ["10.10.10.10", "10.10.10.11"],
        "dns_suffix": "exempel.local", "register_dns": True,
    }]
    if extra_nic:
        nics.append(extra_nic)
    return {
        "_meta": {"tool": "Atlas Server", "format": 1, "collector_version": "1.0.0", "method": "remote",
                  "collected_from": "ADM01", "collected_by": "EXEMPEL\\admin.anna",
                  "collected_utc": "2026-11-26T09:14:00Z", "collected_local": "2026-11-26T10:14:00",
                  "ps_version": "5.1.20348.2849", "elevated": True},
        "system": {
            "computer_name": name, "dns_hostname": name, "domain": "exempel.local", "part_of_domain": True,
            "domain_role": role, "fqdn": f"{name}.exempel.local", "manufacturer": manufacturer, "model": model,
            "memory_bytes": mem_gib * 1024 ** 3, "logical_cpus": cores, "hypervisor_present": True,
            "os_caption": caption, "os_version": f"10.0.{build}", "os_architecture": "64-bit", "os_language": 1053,
            "description": description, "install_date": "2025-01-14T09:31:02", "last_boot": "2026-11-12T03:05:41",
            "registered_org": "Exempel AB", "product_name": caption.replace("Microsoft ", ""),
            "edition_id": "ServerDatacenter", "installation_type": "Server Core" if core else "Server",
            "display_version": "24H2" if build == "26100" else "21H2", "current_build": build, "ubr": ubr,
            "serial_number": "0000-0000-0000-0000-0000-0000-00", "bios_version": "Hyper-V UEFI Release v4.1",
            "cpu_name": "Intel(R) Xeon(R) Gold 6338 CPU @ 2.00GHz", "cpu_sockets": 1, "cpu_cores": cores,
            "time_zone": "(UTC+01:00) Amsterdam, Berlin, Bern, Rome, Stockholm, Vienna", "rdp_enabled": rdp,
        },
        "network": nics,
        "dns": {"primary_suffix": "exempel.local", "search_list": []},
        "features_source": "Get-WindowsFeature",
        "features": feats,
        "services": services,
        "software": software,
        "disks": disks or [
            {"drive": "C:", "label": "", "file_system": "NTFS", "size_bytes": 127 * 1024 ** 3,
             "free_bytes": 71 * 1024 ** 3},
        ],
        "shares": list(shares),
        "updates": {"count": 6, "last_installed": "2026-11-12T00:00:00", "last_id": "KB5046616"},
        "firewall": [{"profile": "Domain", "enabled": True}, {"profile": "Private", "enabled": True},
                     {"profile": "Public", "enabled": True}],
        "_errors": list(errors),
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    dc = server(
        "DC01", "10.10.10.10", "26100", "2894", "Microsoft Windows Server 2025 Datacenter", "Virtual Machine",
        "Microsoft Corporation", 5,
        features(("AD-Domain-Services", "Active Directory Domain Services", "Role", None, 1),
                 ("DNS", "DNS Server", "Role", None, 1),
                 ("GPMC", "Group Policy Management", "Feature", None, 1),
                 ("RSAT", "Remote Server Administration Tools", "Feature", None, 1),
                 ("RSAT-AD-Tools", "AD DS and AD LDS Tools", "Feature", "RSAT-Role-Tools", 3)),
        BASE_SERVICES + [
            svc("NTDS", "Active Directory Domain Services", WIN + r"\lsass.exe"),
            svc("DNS", "DNS Server", WIN + r"\dns.exe"),
            svc("DFSR", "DFS Replication", WIN + r"\DFSRs.exe"),
            svc("Kdc", "Kerberos Key Distribution Center", WIN + r"\lsass.exe"),
            svc("AzureADConnectHealthAgent", "Azure AD Connect Health AD DS Insights Service",
                r"C:\Program Files\Azure Ad Connect Health Adds Agent\Insights\Microsoft.Identity.Health.Adds.InsightsService.exe",
                product="Microsoft Azure AD Connect Health agent for AD DS"),
            svc("SentinelAgent", "Sentinel Agent", r"C:\Program Files\SentinelOne\Sentinel Agent 24.2.3.471\SentinelAgent.exe",
                company="SentinelOne Inc.", product="Sentinel Agent"),
        ],
        base_software() + [
            {"name": "Sentinel Agent", "version": "24.2.3.471", "publisher": "SentinelOne Inc.",
             "install_date": "20250120", "arch": "x64"},
        ],
        shares=[{"name": "NETLOGON", "path": r"C:\Windows\SYSVOL\sysvol\exempel.local\SCRIPTS",
                 "description": "Logon server share"},
                {"name": "SYSVOL", "path": r"C:\Windows\SYSVOL\sysvol", "description": "Logon server share"}],
        description="", core=True, mem_gib=8, cores=2, rdp=False,
    )
    fs = server(
        "FS01", "10.10.10.21", "20348", "3091", "Microsoft Windows Server 2022 Standard", "VMware20,1",
        "VMware, Inc.", 3,
        features(("FS-FileServer", "File Server", "Role Service", "FileAndStorage-Services", 3),
                 ("FS-DFS-Namespace", "DFS Namespaces", "Role Service", "FileAndStorage-Services", 3),
                 ("FS-Resource-Manager", "File Server Resource Manager", "Role Service", "FileAndStorage-Services", 3),
                 ("FS-SMB1", "SMB 1.0/CIFS File Sharing Support", "Feature", None, 1)),
        BASE_SERVICES + [
            svc("SrmSvc", "File Server Resource Manager", WIN + r"\svchost.exe"),
            svc("VMTools", "VMware Tools", r"C:\Program Files\VMware\VMware Tools\vmtoolsd.exe",
                company="VMware, Inc.", product="VMware Tools"),
            svc("VeeamDeploySvc", "Veeam Installer Service", r"C:\Windows\Veeam\Backup\VeeamDeploymentSvc.exe",
                company="Veeam Software Group GmbH", product="Veeam Backup & Replication"),
        ],
        base_software() + [
            {"name": "VMware Tools", "version": "12.4.5.23787635", "publisher": "VMware, Inc.",
             "install_date": "20250203", "arch": "x64"},
        ],
        shares=[{"name": "Gemensam", "path": r"E:\Shares\Gemensam", "description": "Gemensamma filer"},
                {"name": "Hem$", "path": r"E:\Shares\Hem", "description": ""}],
        disks=[{"drive": "C:", "label": "", "file_system": "NTFS", "size_bytes": 80 * 1024 ** 3,
                "free_bytes": 31 * 1024 ** 3},
               {"drive": "E:", "label": "Data", "file_system": "ReFS", "size_bytes": 2048 * 1024 ** 3,
                "free_bytes": 190 * 1024 ** 3}],
        description="Filserver", mem_gib=16, cores=4,
    )
    fs["shares"] = [s for s in fs["shares"] if not s["name"].endswith("$")]
    app = server(
        "APP01", "10.10.10.31", "20348", "3091", "Microsoft Windows Server 2022 Datacenter", "Virtual Machine",
        "Microsoft Corporation", 3,
        features(("Web-Server", "Web Server (IIS)", "Role", None, 1),
                 ("Web-WebServer", "Web Server", "Role Service", "Web-Server", 2),
                 ("Web-Mgmt-Console", "IIS Management Console", "Role Service", "Web-Mgmt-Tools", 3)),
        BASE_SERVICES + [
            svc("W3SVC", "World Wide Web Publishing Service", WIN + r"\svchost.exe"),
            svc("MSSQLSERVER", "SQL Server (MSSQLSERVER)",
                r"C:\Program Files\Microsoft SQL Server\MSSQL16.MSSQLSERVER\MSSQL\Binn\sqlservr.exe",
                path='"C:\\Program Files\\Microsoft SQL Server\\MSSQL16.MSSQLSERVER\\MSSQL\\Binn\\sqlservr.exe" -sMSSQLSERVER',
                account="NT Service\\MSSQLSERVER", product="Microsoft SQL Server"),
            svc("SQLSERVERAGENT", "SQL Server Agent (MSSQLSERVER)",
                r"C:\Program Files\Microsoft SQL Server\MSSQL16.MSSQLSERVER\MSSQL\Binn\SQLAGENT.EXE",
                account="NT Service\\SQLSERVERAGENT", start="Manual", state="Stopped",
                product="Microsoft SQL Server"),
            svc("ExempelAffar", "Exempel Affärssystem Applikationsserver",
                r"D:\Program\Exempel Affärssystem\AppServer.exe", company="Exempel Software AB",
                account="EXEMPEL\\svc-affar", product="Exempel Affärssystem"),
        ],
        base_software() + [
            {"name": "Microsoft SQL Server 2022 (64-bit)", "version": "16.0.4155.4",
             "publisher": "Microsoft Corporation", "install_date": "20250210", "arch": "x64"},
            {"name": "Exempel Affärssystem 9.2", "version": "9.2.1", "publisher": "Exempel Software AB",
             "install_date": "20250212", "arch": "x64"},
        ],
        disks=[{"drive": "C:", "label": "", "file_system": "NTFS", "size_bytes": 100 * 1024 ** 3,
                "free_bytes": 42 * 1024 ** 3},
               {"drive": "D:", "label": "SQL", "file_system": "NTFS", "size_bytes": 500 * 1024 ** 3,
                "free_bytes": 38 * 1024 ** 3}],
        description="Affärssystem och SQL Server",
        extra_nic={"index": 2, "name": "Backup", "description": "Microsoft Hyper-V Network Adapter #2",
                   "mac": "00-15-5D-0A-0B-1F", "dhcp": False,
                   "ipv4": [{"address": "10.10.20.31", "mask": "255.255.255.0"}], "ipv6": [],
                   "gateways": [], "dns_servers": [], "dns_suffix": "", "register_dns": False},
        mem_gib=32, cores=8,
        errors=[{"section": "updates", "message": "Åtkomst nekad (exempel på ett fel i insamlingen)"}],
    )
    for s in (dc, fs, app):
        (OUT / f"atlasserver_{s['system']['computer_name']}_20261126-101400.json").write_text(
            json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Skrev 3 exempelfiler i {OUT}")


if __name__ == "__main__":
    main()
