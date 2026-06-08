param(
    [string]$ProjectRoot = "D:\Documents\Utilcode\github\github-radar",
    [string]$Python = "python"
)

Set-Location -LiteralPath $ProjectRoot
& $Python -m github_radar.gui
