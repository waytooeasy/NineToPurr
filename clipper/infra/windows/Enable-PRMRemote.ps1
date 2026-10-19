<#
  Enable-PRMRemote.ps1  -  every remote-access path on Windows 11, then a PASS/FAIL check.

  Turns on: RDP (+NLA), OpenSSH Server, WinRM/PowerShell Remoting, SMB file sharing + network
  discovery, ping, Remote Assistance, Remote Registry, Tailscale, RustDesk (GUI, works on Home),
  Wake-on-LAN, no sleep, fast startup off.

  Firewall scope: default = Tailscale (100.64.0.0/10) + home LAN.  -OpenToAll = any address.

  Run (PowerShell as Administrator):
    Set-ExecutionPolicy -Scope Process Bypass -Force; .\Enable-PRMRemote.ps1
    .\Enable-PRMRemote.ps1 -OpenToAll      # no source restriction
    .\Enable-PRMRemote.ps1 -CheckOnly      # checks only, no changes
#>
param([switch]$CheckOnly, [switch]$OpenToAll)
$ErrorActionPreference = 'Continue'

if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "Run this as Administrator." -ForegroundColor Red; exit 1
}

$Scope   = if ($OpenToAll) { 'Any' } else { @('100.64.0.0/10', 'LocalSubnet') }
$edition = (Get-CimInstance Win32_OperatingSystem).Caption
$isPro   = $edition -notmatch 'Home'
Write-Host "Windows: $edition | firewall scope: $($Scope -join ', ')" -ForegroundColor Cyan
function Step($m) { Write-Host "`n== $m" -ForegroundColor Cyan }
function Open-Group($g) {
    Get-NetFirewallRule -DisplayGroup $g -ErrorAction SilentlyContinue |
        Where-Object Direction -eq 'Inbound' | Set-NetFirewallRule -Enabled True -RemoteAddress $Scope
}

if (-not $CheckOnly) {
    # Private network profile (sharing/discovery rules need it)
    Get-NetConnectionProfile | Where-Object NetworkCategory -eq 'Public' |
        Set-NetConnectionProfile -NetworkCategory Private -ErrorAction SilentlyContinue

    Step "RDP"
    if ($isPro) {
        Set-ItemProperty 'HKLM:\System\CurrentControlSet\Control\Terminal Server' fDenyTSConnections 0
        Set-ItemProperty 'HKLM:\System\CurrentControlSet\Control\Terminal Server\WinStations\RDP-Tcp' UserAuthentication 1
        Set-Service TermService -StartupType Automatic; Start-Service TermService
        Open-Group 'Remote Desktop'
    } else { Write-Host "Home edition: no RDP server. RustDesk below covers the GUI." -ForegroundColor Yellow }

    Step "OpenSSH Server"
    $cap = Get-WindowsCapability -Online -Name 'OpenSSH.Server*'
    if ($cap.State -ne 'Installed') { Add-WindowsCapability -Online -Name $cap.Name | Out-Null }
    Set-Service sshd -StartupType Automatic; Start-Service sshd
    Set-Service ssh-agent -StartupType Automatic -ErrorAction SilentlyContinue
    New-ItemProperty 'HKLM:\SOFTWARE\OpenSSH' DefaultShell -Value "$env:WINDIR\System32\WindowsPowerShell\v1.0\powershell.exe" -PropertyType String -Force | Out-Null
    if (Get-NetFirewallRule -Name 'OpenSSH-Server-In-TCP' -ErrorAction SilentlyContinue) {
        Set-NetFirewallRule -Name 'OpenSSH-Server-In-TCP' -Enabled True -RemoteAddress $Scope
    } else {
        New-NetFirewallRule -Name 'OpenSSH-Server-In-TCP' -DisplayName 'OpenSSH Server (sshd)' -Direction Inbound -Protocol TCP -LocalPort 22 -Action Allow -RemoteAddress $Scope | Out-Null
    }

    Step "WinRM / PowerShell Remoting"
    Enable-PSRemoting -Force -SkipNetworkProfileCheck | Out-Null
    Set-Service WinRM -StartupType Automatic
    Open-Group 'Windows Remote Management'

    Step "File sharing, network discovery, ping"
    Open-Group 'File and Printer Sharing'
    Open-Group 'Network Discovery'
    foreach ($s in 'FDResPub','fdPHost','SSDPSRV','upnphost','LanmanServer') {
        Set-Service $s -StartupType Automatic -ErrorAction SilentlyContinue; Start-Service $s -ErrorAction SilentlyContinue
    }
    if (-not (Get-NetFirewallRule -Name 'PRM-ICMPv4-In' -ErrorAction SilentlyContinue)) {
        New-NetFirewallRule -Name 'PRM-ICMPv4-In' -DisplayName 'PRM Ping (ICMPv4)' -Protocol ICMPv4 -IcmpType 8 -Direction Inbound -Action Allow -RemoteAddress $Scope | Out-Null
    }

    Step "Remote Assistance + Remote Registry"
    Set-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\Remote Assistance' fAllowToGetHelp 1
    Open-Group 'Remote Assistance'
    Set-Service RemoteRegistry -StartupType Automatic; Start-Service RemoteRegistry

    Step "Tailscale"
    $ts = "$env:ProgramFiles\Tailscale\tailscale.exe"
    if (-not (Test-Path $ts)) { winget install --id Tailscale.Tailscale -e --silent --accept-package-agreements --accept-source-agreements }
    if (Test-Path $ts) {
        Set-Service Tailscale -StartupType Automatic -ErrorAction SilentlyContinue
        & $ts set --unattended=true 2>$null
        if (-not (& $ts ip -4 2>$null)) { Write-Host "Log in to Tailscale (browser opens):" -ForegroundColor Yellow; & $ts up --unattended }
    }

    Step "RustDesk (GUI remote, works without RDP)"
    if (-not (Get-Service RustDesk -ErrorAction SilentlyContinue)) {
        winget install --id RustDesk.RustDesk -e --silent --accept-package-agreements --accept-source-agreements
    }
    Set-Service RustDesk -StartupType Automatic -ErrorAction SilentlyContinue; Start-Service RustDesk -ErrorAction SilentlyContinue

    Step "Wake-on-LAN, no sleep, fast startup off"
    Get-NetAdapter -Physical | Where-Object Status -eq 'Up' | ForEach-Object {
        Set-NetAdapterAdvancedProperty -Name $_.Name -DisplayName 'Wake on Magic Packet' -DisplayValue 'Enabled' -ErrorAction SilentlyContinue
        Set-NetAdapterPowerManagement -Name $_.Name -WakeOnMagicPacket Enabled -ErrorAction SilentlyContinue
        powercfg /deviceenablewake "$($_.InterfaceDescription)" 2>$null
    }
    Set-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Power' HiberbootEnabled 0
    powercfg /change standby-timeout-ac 0; powercfg /change hibernate-timeout-ac 0; powercfg /change monitor-timeout-ac 15
    Write-Host "WoL also needs 'Wake on LAN / Power on by PCI-E' enabled in BIOS." -ForegroundColor Yellow
}

# ================= CHECKS =================
Step "Checks"
$r = [System.Collections.Generic.List[object]]::new()
function Check($n, [bool]$ok, $d = '') { $r.Add([pscustomobject]@{Check = $n; Result = $(if ($ok) { 'PASS' } else { 'FAIL' }); Detail = $d }) }
function Listening($p) { [bool](Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue) }
function Running($s) { (Get-Service $s -ErrorAction SilentlyContinue).Status -eq 'Running' }

$ts = "$env:ProgramFiles\Tailscale\tailscale.exe"
$tsIp = if (Test-Path $ts) { & $ts ip -4 2>$null | Select-Object -First 1 } else { $null }
$lanIp = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.PrefixOrigin -in 'Dhcp','Manual' -and $_.IPAddress -notlike '100.*' } | Select-Object -First 1).IPAddress
function Reach($p) { if ($tsIp) { (Test-NetConnection $tsIp -Port $p -WarningAction SilentlyContinue).TcpTestSucceeded } else { $false } }

if ($isPro) {
    Check 'RDP service + :3389' ((Running TermService) -and (Listening 3389)) "mstsc /v:$tsIp"
    Check 'RDP via Tailscale' (Reach 3389)
} else { Check 'RDP' $true 'Home edition - use RustDesk' }
Check 'SSH sshd + :22'      ((Running sshd) -and (Listening 22)) "ssh $env:USERNAME@$tsIp"
Check 'SSH via Tailscale'   (Reach 22)
Check 'WinRM + :5985'       ((Running WinRM) -and (Listening 5985)) "Enter-PSSession $tsIp -Credential $env:USERNAME"
Check 'WinRM via Tailscale' (Reach 5985)
Check 'SMB + :445'          ((Running LanmanServer) -and (Listening 445)) "\\$tsIp\C$"
Check 'Remote Registry'     (Running RemoteRegistry)
Check 'Remote Assistance'   ((Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\Remote Assistance').fAllowToGetHelp -eq 1)
Check 'Ping rule'           ([bool](Get-NetFirewallRule -Name 'PRM-ICMPv4-In' -ErrorAction SilentlyContinue))
Check 'Tailscale connected' ([bool]$tsIp) "$tsIp"
Check 'RustDesk running'    (Running RustDesk) 'open RustDesk -> note ID + set a permanent password'
$sleep = (powercfg /query SCHEME_CURRENT SUB_SLEEP STANDBYIDLE | Select-String 'Current AC Power Setting Index' | ForEach-Object { ($_ -split ':')[-1].Trim() })
Check 'Never sleeps on AC'  ($sleep -eq '0x00000000')
Check 'Fast startup off'    ((Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Power').HiberbootEnabled -eq 0)
$wol = Get-NetAdapter -Physical | Where-Object Status -eq 'Up' | Get-NetAdapterPowerManagement -ErrorAction SilentlyContinue
Check 'Wake-on-LAN (NIC)'   ([bool]($wol | Where-Object WakeOnMagicPacket -eq 'Enabled')) "LAN IP $lanIp, MAC $((Get-NetAdapter -Physical | Where-Object Status -eq 'Up' | Select-Object -First 1).MacAddress)"
Check 'VMware services'     ([bool](Get-Service VMAuthdService -ErrorAction SilentlyContinue)) 'needed for the clipper VM'

$r | Format-Table -AutoSize
$f = ($r | Where-Object Result -eq 'FAIL').Count
if ($f) { Write-Host "$f check(s) failed. Paste this table to Claude." -ForegroundColor Red }
else { Write-Host "All remote paths up. Tailscale IP: $tsIp" -ForegroundColor Green }
