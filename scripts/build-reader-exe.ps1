param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$Python = "python"
)

Set-Location -LiteralPath $ProjectRoot

& $Python -c "import PySide6.QtCore, PySide6.QtGui, PySide6.QtWidgets; import github_radar.reader_app; print('PySide6 reader dependencies OK')"
if ($LASTEXITCODE -ne 0) {
    Write-Error "Reader dependencies are incomplete. Install project dependencies and PySide6 before packaging."
    exit $LASTEXITCODE
}

& $Python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name GitHubRadarReader `
    --icon "assets\app-icon.ico" `
    --paths "." `
    --hidden-import PySide6.QtCore `
    --hidden-import PySide6.QtGui `
    --hidden-import PySide6.QtWidgets `
    "scripts\reader_launcher.py"

if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

$exePath = Join-Path $ProjectRoot "dist\GitHubRadarReader.exe"
$exe = Get-Item -LiteralPath $exePath
$minSize = 25MB
if ($exe.Length -lt $minSize) {
    Write-Error "Built exe is unexpectedly small ($([math]::Round($exe.Length / 1MB, 2)) MB). PySide6/Qt files were likely not bundled."
    exit 1
}

$smokeDir = Join-Path $ProjectRoot "build\reader-smoke"
New-Item -ItemType Directory -Force -Path $smokeDir | Out-Null
$smokeConfig = Join-Path $smokeDir "radar.toml"
if (Test-Path -LiteralPath $smokeConfig) {
    Remove-Item -LiteralPath $smokeConfig -Force
}

$process = Start-Process `
    -FilePath $exePath `
    -ArgumentList @("--init-config", "--config", "`"$smokeConfig`"") `
    -Wait `
    -PassThru `
    -WindowStyle Hidden

if ($process.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $smokeConfig)) {
    Write-Error "Built exe smoke test failed. Exit code: $($process.ExitCode)"
    exit 1
}

Remove-Item -LiteralPath $smokeConfig -Force
Remove-Item -LiteralPath $smokeDir -Force

Write-Host "Built: $exePath"
Write-Host "Size: $([math]::Round($exe.Length / 1MB, 2)) MB"
Write-Host "Smoke test: OK"
