param(
  [string]$LocalIp = "192.168.1.172",
  [string]$CameraIp = "192.168.1.173",
  [int]$PrefixLength = 24,
  [string]$ProbeIp = "10.10.10.1"
)

$ErrorActionPreference = "Stop"

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
  [Security.Principal.WindowsBuiltInRole]::Administrator
)

if (-not $isAdmin) {
  throw "Please run this script from an Administrator PowerShell."
}

$probeAddress = Get-NetIPAddress -AddressFamily IPv4 -IPAddress $ProbeIp -ErrorAction SilentlyContinue |
  Select-Object -First 1

if (-not $probeAddress) {
  throw "Could not find the Ethernet adapter with $ProbeIp. Connect the camera LAN first."
}

$ifIndex = $probeAddress.InterfaceIndex
$adapter = Get-NetAdapter -InterfaceIndex $ifIndex

$existingAddress = Get-NetIPAddress -InterfaceIndex $ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue |
  Where-Object { $_.IPAddress -eq $LocalIp }

if (-not $existingAddress) {
  New-NetIPAddress -InterfaceIndex $ifIndex -IPAddress $LocalIp -PrefixLength $PrefixLength -AddressFamily IPv4 | Out-Null
}

Set-NetIPInterface -InterfaceIndex $ifIndex -AddressFamily IPv4 -InterfaceMetric 5

Get-NetRoute -DestinationPrefix "$CameraIp/32" -AddressFamily IPv4 -ErrorAction SilentlyContinue |
  Remove-NetRoute -Confirm:$false -ErrorAction SilentlyContinue

New-NetRoute -DestinationPrefix "$CameraIp/32" -InterfaceIndex $ifIndex -NextHop "0.0.0.0" -RouteMetric 1 | Out-Null

Write-Host "Configured $($adapter.Name) with $LocalIp/$PrefixLength and a host route to $CameraIp."
Write-Host ""
Test-NetConnection -ComputerName $CameraIp -Port 5000
