param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$Python = "python"
)

Set-Location -LiteralPath $ProjectRoot
& $Python -m github_radar.gui
