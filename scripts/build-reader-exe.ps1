param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$Python = "python"
)

Set-Location -LiteralPath $ProjectRoot

& $Python -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --name GitHubRadarReader `
    --icon "assets\app-icon.ico" `
    --paths "." `
    --add-data "radar.toml:." `
    "scripts\reader_launcher.py"

if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Host "Built: $ProjectRoot\dist\GitHubRadarReader\GitHubRadarReader.exe"
