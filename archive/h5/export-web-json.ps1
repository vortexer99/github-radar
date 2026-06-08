param(
    [string]$ProjectRoot = "D:\Documents\Utilcode\github\github-radar",
    [string]$Python = "python",
    [string]$Feedback = ""
)

Set-Location -LiteralPath $ProjectRoot
if ($Feedback) {
    & $Python -m github_radar.web_export --config radar.toml --feedback $Feedback
} else {
    & $Python -m github_radar.web_export --config radar.toml
}
