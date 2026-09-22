$ErrorActionPreference = "Stop"

$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $projectDir

python -m pip install -r requirements-dev.txt
python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name "VPN-Speed-Tester" `
    --version-file "version_info.txt" `
    "vpn_speed_tester.py"

$releaseDir = Join-Path $projectDir "release"
New-Item -ItemType Directory -Force -Path $releaseDir | Out-Null
$exePath = Join-Path $projectDir "dist\VPN-Speed-Tester.exe"
$zipPath = Join-Path $releaseDir "VPN-Speed-Tester-v1.0.0-windows-x64.zip"

Compress-Archive -LiteralPath $exePath -DestinationPath $zipPath -Force
Write-Host "Build complete: $exePath"
Write-Host "Release package: $zipPath"
