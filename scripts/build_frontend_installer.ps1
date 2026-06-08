param(
  [string]$OutputName = "ASV-Safety-Camera-Setup.exe"
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$ReleaseDir = Join-Path $RepoRoot "release"
$BuildDir = Join-Path $ReleaseDir "installer-source"
$PayloadRoot = Join-Path $BuildDir "payload"
$FrontendDir = Join-Path $PayloadRoot "frontend"
$PayloadZip = Join-Path $BuildDir "payload.zip"
$SetupExe = Join-Path $ReleaseDir $OutputName
$SedFile = Join-Path $BuildDir "asv-installer.sed"

New-Item -ItemType Directory -Force -Path $ReleaseDir | Out-Null
if (Test-Path $BuildDir) {
  Remove-Item -LiteralPath $BuildDir -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $FrontendDir | Out-Null

powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "generate_asv_icon.ps1") | Out-Null

Push-Location $RepoRoot
try {
  $previousRouterMode = $env:VITE_ROUTER_MODE
  $env:VITE_ROUTER_MODE = "hash"
  npm run build -- --base ./
  $env:VITE_ROUTER_MODE = $previousRouterMode
}
finally {
  Pop-Location
}

Copy-Item -Path (Join-Path $RepoRoot "dist\*") -Destination $FrontendDir -Recurse -Force

$Launcher = @'
@echo off
set "APP_DIR=%~dp0"
start "ASV Safety Camera" powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%APP_DIR%start-asv-camera.ps1"
exit /b 0
'@
Set-Content -LiteralPath (Join-Path $PayloadRoot "start-asv-camera.cmd") -Value $Launcher -Encoding ASCII

$ServerScript = @'
$ErrorActionPreference = "Stop"

$AppDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Join-Path $AppDir "frontend"
$Port = 51730
$Url = "http://127.0.0.1:$Port/"

function Open-App {
  Start-Process $Url
}

$listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Parse("127.0.0.1"), $Port)
try {
  $listener.Start()
} catch {
  Open-App
  exit 0
}

Open-App

$mimeTypes = @{
  ".html" = "text/html; charset=utf-8"
  ".js" = "text/javascript; charset=utf-8"
  ".css" = "text/css; charset=utf-8"
  ".json" = "application/json; charset=utf-8"
  ".png" = "image/png"
  ".jpg" = "image/jpeg"
  ".jpeg" = "image/jpeg"
  ".svg" = "image/svg+xml"
  ".ico" = "image/x-icon"
  ".woff" = "font/woff"
  ".woff2" = "font/woff2"
}

function Resolve-FrontendPath([string]$RequestTarget) {
  $clean = ($RequestTarget -split "\?")[0]
  if ([string]::IsNullOrWhiteSpace($clean) -or $clean -eq "/") {
    $clean = "/index.html"
  }

  $decoded = [Uri]::UnescapeDataString($clean)
  $relative = $decoded.TrimStart("/").Replace("/", [IO.Path]::DirectorySeparatorChar)
  $candidate = [IO.Path]::GetFullPath((Join-Path $Root $relative))
  $rootFull = [IO.Path]::GetFullPath($Root)

  if (-not $candidate.StartsWith($rootFull, [StringComparison]::OrdinalIgnoreCase)) {
    return Join-Path $Root "index.html"
  }

  if (Test-Path -LiteralPath $candidate -PathType Leaf) {
    return $candidate
  }

  return Join-Path $Root "index.html"
}

function Send-Response($Stream, [int]$Status, [string]$ContentType, [byte[]]$Body) {
  $statusText = if ($Status -eq 200) { "OK" } else { "Internal Server Error" }
  $header = "HTTP/1.1 $Status $statusText`r`nContent-Type: $ContentType`r`nContent-Length: $($Body.Length)`r`nCache-Control: no-store`r`nConnection: close`r`n`r`n"
  $headerBytes = [Text.Encoding]::ASCII.GetBytes($header)
  $Stream.Write($headerBytes, 0, $headerBytes.Length)
  if ($Body.Length -gt 0) {
    $Stream.Write($Body, 0, $Body.Length)
  }
}

while ($true) {
  $client = $listener.AcceptTcpClient()
  try {
    $stream = $client.GetStream()
    $reader = [IO.StreamReader]::new($stream, [Text.Encoding]::ASCII, $false, 1024, $true)
    $requestLine = $reader.ReadLine()
    while ($true) {
      $line = $reader.ReadLine()
      if ($null -eq $line -or $line -eq "") { break }
    }

    $target = "/"
    if ($requestLine -match "^[A-Z]+\s+([^\s]+)") {
      $target = $matches[1]
    }

    $filePath = Resolve-FrontendPath $target
    $ext = [IO.Path]::GetExtension($filePath).ToLowerInvariant()
    $mime = if ($mimeTypes.ContainsKey($ext)) { $mimeTypes[$ext] } else { "application/octet-stream" }
    $bytes = [IO.File]::ReadAllBytes($filePath)
    Send-Response $stream 200 $mime $bytes
  } catch {
    try {
      $message = [Text.Encoding]::UTF8.GetBytes("Failed to load ASV Safety Camera.")
      Send-Response $stream 500 "text/plain; charset=utf-8" $message
    } catch {}
  } finally {
    $client.Close()
  }
}
'@
Set-Content -LiteralPath (Join-Path $PayloadRoot "start-asv-camera.ps1") -Value $ServerScript -Encoding UTF8

$InstallCmd = @'
@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
'@
Set-Content -LiteralPath (Join-Path $BuildDir "install.cmd") -Value $InstallCmd -Encoding ASCII

$InstallPs1 = @'
$ErrorActionPreference = "Stop"

$SourceDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$AppDir = Join-Path $env:LOCALAPPDATA "ASV Safety Camera"
$FrontendDir = Join-Path $AppDir "frontend"

New-Item -ItemType Directory -Force -Path $AppDir | Out-Null

if (Test-Path $FrontendDir) {
  Remove-Item -LiteralPath $FrontendDir -Recurse -Force
}

Expand-Archive -LiteralPath (Join-Path $SourceDir "payload.zip") -DestinationPath $AppDir -Force

$ShortcutTarget = Join-Path $AppDir "start-asv-camera.cmd"
$IconPath = Join-Path $AppDir "frontend\favicon.ico"
$Shell = New-Object -ComObject WScript.Shell

$DesktopShortcut = $Shell.CreateShortcut((Join-Path ([Environment]::GetFolderPath("Desktop")) "ASV Safety Camera.lnk"))
$DesktopShortcut.TargetPath = $ShortcutTarget
$DesktopShortcut.WorkingDirectory = $AppDir
if (Test-Path $IconPath) {
  $DesktopShortcut.IconLocation = $IconPath
}
$DesktopShortcut.Save()

$StartMenuDir = Join-Path ([Environment]::GetFolderPath("Programs")) "ASV"
New-Item -ItemType Directory -Force -Path $StartMenuDir | Out-Null
$StartShortcut = $Shell.CreateShortcut((Join-Path $StartMenuDir "ASV Safety Camera.lnk"))
$StartShortcut.TargetPath = $ShortcutTarget
$StartShortcut.WorkingDirectory = $AppDir
if (Test-Path $IconPath) {
  $StartShortcut.IconLocation = $IconPath
}
$StartShortcut.Save()

Start-Process -FilePath $ShortcutTarget -WorkingDirectory $AppDir
'@
Set-Content -LiteralPath (Join-Path $BuildDir "install.ps1") -Value $InstallPs1 -Encoding UTF8

Compress-Archive -LiteralPath (Join-Path $PayloadRoot "frontend"), (Join-Path $PayloadRoot "start-asv-camera.cmd"), (Join-Path $PayloadRoot "start-asv-camera.ps1") -DestinationPath $PayloadZip -Force

$SourceDirForSed = $BuildDir.TrimEnd("\")
$Sed = @"
[Version]
Class=IEXPRESS
SEDVersion=3
[Options]
PackagePurpose=InstallApp
ShowInstallProgramWindow=0
HideExtractAnimation=1
UseLongFileName=1
InsideCompressed=0
CAB_FixedSize=0
CAB_ResvCodeSigning=0
RebootMode=N
InstallPrompt=
DisplayLicense=
FinishMessage=ASV Safety Camera installed.
TargetName=$SetupExe
FriendlyName=ASV Safety Camera Setup
AppLaunched=cmd /c install.cmd
PostInstallCmd=<None>
AdminQuietInstCmd=cmd /c install.cmd
UserQuietInstCmd=cmd /c install.cmd
SourceFiles=SourceFiles
[Strings]
FILE0="payload.zip"
FILE1="install.cmd"
FILE2="install.ps1"
[SourceFiles]
SourceFiles0=$SourceDirForSed
[SourceFiles0]
%FILE0%=
%FILE1%=
%FILE2%=
"@
Set-Content -LiteralPath $SedFile -Value $Sed -Encoding ASCII

if (Test-Path $SetupExe) {
  Remove-Item -LiteralPath $SetupExe -Force
}

$IExpress = Join-Path $env:SystemRoot "System32\iexpress.exe"
& $IExpress /N /Q $SedFile

$deadline = (Get-Date).AddSeconds(15)
while (-not (Test-Path $SetupExe) -and (Get-Date) -lt $deadline) {
  Start-Sleep -Milliseconds 250
}

if (-not (Test-Path $SetupExe)) {
  throw "Installer was not created: $SetupExe"
}

Get-Item $SetupExe
