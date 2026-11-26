@echo off
rem Atlas Server: startar insamlaren med Windows PowerShell. Bara lasande.
rem Exempel: Collect-AtlasServer.cmd   eller   Collect-AtlasServer.cmd -ComputerName SRV01,SRV02
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Collect-AtlasServer.ps1" %*
echo.
if "%ATLAS_NOPAUSE%"=="" pause
