param(
    [string]$ProjectRoot = $(if (
        (Test-Path -LiteralPath (Join-Path $PSScriptRoot "GitHubRadarReader.exe")) -or
        (Test-Path -LiteralPath (Join-Path $PSScriptRoot "dist\GitHubRadarReader.exe")) -or
        (Test-Path -LiteralPath (Join-Path $PSScriptRoot "GitHubRadarReader\GitHubRadarReader.exe")) -or
        (Test-Path -LiteralPath (Join-Path $PSScriptRoot "dist\GitHubRadarReader\GitHubRadarReader.exe"))
    ) { $PSScriptRoot } else { (Resolve-Path (Join-Path $PSScriptRoot "..")).Path }),
    [string]$Python = "python",
    [switch]$AssumeYes
)

Set-Location -LiteralPath $ProjectRoot

$configPath = Join-Path $ProjectRoot "radar.toml"
$configExists = Test-Path -LiteralPath $configPath
$reportDir = Join-Path $ProjectRoot "reports"
$logPath = Join-Path $ProjectRoot "run-radar.log"
$exeCandidates = @(
    (Join-Path $ProjectRoot "GitHubRadarReader.exe"),
    (Join-Path $ProjectRoot "dist\GitHubRadarReader.exe"),
    (Join-Path $ProjectRoot "GitHubRadarReader\GitHubRadarReader.exe"),
    (Join-Path $ProjectRoot "dist\GitHubRadarReader\GitHubRadarReader.exe")
)
$readerExe = $exeCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1

$defaultConfig = @'
# GitHub Radar local configuration.
# GitHub Token can be configured in the reader settings or with GITHUB_TOKEN.

db_path = "data/radar.db"
report_dir = "reports"
min_stars = 100
per_page = 50
created_within_days = 45
pushed_within_days = 14
exploration_ratio = 0.25

languages = []
excluded_terms = []

query_templates = [
  "created:>{created_since} stars:>{min_stars}",
  "pushed:>{pushed_since} stars:>{min_stars}",
  "topic:ai pushed:>{pushed_since} stars:>{min_stars}",
  "topic:llm pushed:>{pushed_since} stars:>{min_stars}",
  "topic:developer-tools pushed:>{pushed_since} stars:>{min_stars}",
  "topic:security pushed:>{pushed_since} stars:>{min_stars}",
  "topic:database pushed:>{pushed_since} stars:>{min_stars}",
  "topic:cli pushed:>{pushed_since} stars:>{min_stars}"
]
'@

$runNow = $true
if (-not $configExists) {
    try {
        $utf8NoBom = New-Object System.Text.UTF8Encoding $false
        [System.IO.File]::WriteAllText($configPath, $defaultConfig, $utf8NoBom)
    } catch {
        if (-not $AssumeYes) {
            Read-Host "Failed to create config: $($_.Exception.Message). Press Enter to close"
        }
        exit 1
    }

    Write-Host "Created default config: $configPath"
    Write-Host "You can edit radar.toml or set GitHub Token in the reader settings before fetching."
    if (-not $AssumeYes) {
        $answer = Read-Host "Fetch GitHub data now? [y/N]"
        $runNow = $answer.Trim().ToLowerInvariant() -in @("y", "yes")
    }
}

if (-not $runNow) {
    Write-Host "Skipped fetching. Run this script again when you are ready."
    if (-not $AssumeYes) {
        Read-Host "Press Enter to close"
    }
    exit 0
}

$runStartedAt = Get-Date
Add-Content -LiteralPath $logPath -Encoding UTF8 -Value ""
Add-Content -LiteralPath $logPath -Encoding UTF8 -Value "=== run-radar.ps1 $($runStartedAt.ToString('s')) ==="
if ($readerExe) {
    $arguments = @("--run", "--config", "`"$configPath`"", "--log", "`"$logPath`"")
    $process = Start-Process -FilePath $readerExe -ArgumentList $arguments -Wait -PassThru
    $exitCode = $process.ExitCode
} else {
    & $Python -m github_radar run --config $configPath *>> $logPath
    $exitCode = if ($null -ne $LASTEXITCODE) { [int]$LASTEXITCODE } elseif ($?) { 0 } else { 1 }
}

$newReport = $false
if (Test-Path -LiteralPath $reportDir) {
    $newReport = [bool](Get-ChildItem -LiteralPath $reportDir -Filter "github-radar-*.md" -File -ErrorAction SilentlyContinue |
        Where-Object { $_.LastWriteTime -ge $runStartedAt } |
        Select-Object -First 1)
}
if ($exitCode -eq 0 -and -not $newReport) {
    Write-Host "No new report was generated. Collection may have failed before writing reports."
    $exitCode = 1
}
if ($exitCode -ne 0 -and (Test-Path -LiteralPath $logPath)) {
    Write-Host ""
    Write-Host "Last log lines from $logPath"
    Get-Content -LiteralPath $logPath -Tail 40
}

if (-not $AssumeYes) {
    if ($exitCode -eq 0) {
        Read-Host "Finished. Press Enter to close"
    } else {
        Read-Host "Failed with exit code $exitCode. Press Enter to close"
    }
}
exit $exitCode
