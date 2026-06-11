param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$Python = "python"
)

Set-Location -LiteralPath $ProjectRoot

& $Python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name GitHubRadarReader `
    --icon "assets\app-icon.ico" `
    --paths "." `
    "scripts\reader_launcher.py"

if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Host "Built: $ProjectRoot\dist\GitHubRadarReader.exe"
