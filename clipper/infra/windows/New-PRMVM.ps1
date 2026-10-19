<#
  New-PRMVM.ps1  -  create the clipper VM on Hyper-V (Windows 11 Pro), auto-starts with Windows.
  VM: "prm-clipper", Gen2, 6 vCPU, 8 GB RAM, 80 GB disk, Ubuntu Server 24.04 LTS.

  Run as Administrator:
    Set-ExecutionPolicy -Scope Process Bypass -Force; .\New-PRMVM.ps1
  1st run enables Hyper-V and asks to reboot. Run it again after the reboot.
  Note: creating the external switch drops the network for ~5 s (run it locally, not over RDP).
#>
$ErrorActionPreference = 'Stop'
$Name = 'prm-clipper'; $Root = 'C:\PRM\vm'; $Switch = 'PRM-External'
$CPU = 6; $RAM = 8GB; $Disk = 80GB

if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)) { Write-Host "Run as Administrator." -ForegroundColor Red; exit 1 }

# 1. Hyper-V
$hv = Get-WindowsOptionalFeature -Online -FeatureName Microsoft-Hyper-V-All
if ($hv.State -ne 'Enabled') {
    Enable-WindowsOptionalFeature -Online -FeatureName Microsoft-Hyper-V-All -All -NoRestart | Out-Null
    Write-Host "Hyper-V enabled. REBOOT, then run this script again." -ForegroundColor Yellow
    exit 0
}
Import-Module Hyper-V

# 2. Ubuntu Server 24.04 ISO (latest point release)
New-Item -ItemType Directory -Force $Root | Out-Null
$base = 'https://releases.ubuntu.com/24.04/'
$isoName = ((Invoke-WebRequest $base -UseBasicParsing).Links.href |
    Where-Object { $_ -match '^ubuntu-24\.04(\.\d+)?-live-server-amd64\.iso$' } | Sort-Object | Select-Object -Last 1)
if (-not $isoName) { throw "Could not find the Ubuntu ISO at $base" }
$iso = Join-Path $Root $isoName
if (-not (Test-Path $iso)) {
    Write-Host "Downloading $isoName (~3 GB)..."
    Start-BitsTransfer -Source ($base + $isoName) -Destination $iso
}

# 3. External switch on the NIC that has the default route
if (-not (Get-VMSwitch -Name $Switch -ErrorAction SilentlyContinue)) {
    $ifIndex = (Get-NetRoute -DestinationPrefix '0.0.0.0/0' | Sort-Object RouteMetric | Select-Object -First 1).InterfaceIndex
    $nic = Get-NetAdapter -InterfaceIndex $ifIndex
    Write-Host "Creating external switch on '$($nic.Name)' (network blips for a few seconds)..."
    New-VMSwitch -Name $Switch -NetAdapterName $nic.Name -AllowManagementOS $true | Out-Null
}

# 4. VM
if (-not (Get-VM -Name $Name -ErrorAction SilentlyContinue)) {
    $vhd = Join-Path $Root "$Name.vhdx"
    New-VM -Name $Name -Generation 2 -MemoryStartupBytes $RAM -NewVHDPath $vhd -NewVHDSizeBytes $Disk `
           -SwitchName $Switch -Path $Root | Out-Null
    Set-VM -Name $Name -ProcessorCount $CPU -StaticMemory -CheckpointType Disabled `
           -AutomaticStartAction Start -AutomaticStartDelay 30 -AutomaticStopAction ShutDown
    Set-VMFirmware -VMName $Name -SecureBootTemplate MicrosoftUEFICertificateAuthority
    Add-VMDvdDrive -VMName $Name -Path $iso
    Set-VMFirmware -VMName $Name -FirstBootDevice (Get-VMDvdDrive -VMName $Name)
    Enable-VMIntegrationService -VMName $Name -Name 'Guest Service Interface'
}
Start-VM -Name $Name
vmconnect.exe localhost $Name

Write-Host @"

VM '$Name' is booting the Ubuntu installer (window opened). In the installer:
  - Language English, keyboard your layout, 'Ubuntu Server' (not minimized)
  - Network: DHCP is fine
  - Storage: use entire disk (default)
  - Profile: user 'prm', a strong password, server name 'prm-clipper'
  - [X] Install OpenSSH server
  - No snaps. Finish, then 'Reboot Now' (press Enter if it asks to remove the media)
After the reboot, log in and run:
  curl -fsSL https://tailscale.com/install.sh | sh && sudo tailscale up --ssh
Then tell Claude 'VM up'.
"@ -ForegroundColor Green
# VM auto-starts 30 s after Windows boots (AutomaticStartAction=Start).
