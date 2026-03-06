param(
    [switch]$Setup,
    [switch]$PytestQuick,
    [switch]$PytestVerbose,
    [switch]$PytestLoop,
    [switch]$HelpChecks,
    [switch]$SmokeCore,
    [switch]$ResumeChecks,
    [switch]$DuplicateChecks,
    [switch]$DiffChecks,
    [switch]$ErrorChecks,
    [switch]$BudgetChecks,
    [switch]$OutputChecks,
    [switch]$RegressionPack,
    [switch]$All,

    [string]$Site = "https://www.dedicatodesign.com",
    [int]$MaxPages = 5,
    [int]$PlaywrightPages = 3,
    [int]$PytestLoops = 5
)

$ErrorActionPreference = "Stop"

function Write-Step($msg) {
    Write-Host ""
    Write-Host "==> $msg" -ForegroundColor Cyan
}

function Run-Cmd([string]$cmd) {
    Write-Host "PS> $cmd" -ForegroundColor DarkGray
    Invoke-Expression $cmd
    if ($LASTEXITCODE -ne 0) {
        throw ("Command failed with exit code {0}: {1}" -f $LASTEXITCODE, $cmd)
    }
}

function Ensure-Dirs {
    New-Item -ItemType Directory -Force -Path "runs" | Out-Null
    New-Item -ItemType Directory -Force -Path "diffs" | Out-Null
}

function Test-Setup {
    Write-Step "Installing dev requirements"
    Run-Cmd 'py -m pip install -r requirements-dev.txt'
    Run-Cmd 'py --version'
    Run-Cmd 'py -m pytest --version'
}

function Test-PytestQuick {
    Write-Step "Running pytest quick"
    Run-Cmd 'py -m pytest -q'
}

function Test-PytestVerbose {
    Write-Step "Running pytest verbose"
    Run-Cmd 'py -m pytest -vv'
}

function Test-PytestLoop {
    Write-Step "Running pytest loop"
    for ($i=1; $i -le $PytestLoops; $i++) {
        Write-Host "Loop $i / $PytestLoops" -ForegroundColor Yellow
        Run-Cmd 'py -m pytest -q'
    }
}

function Test-HelpChecks {
    Write-Step "Checking CLI help"
    Run-Cmd 'py site_audit.py --help'
    Run-Cmd 'py site_audit.py crawl --help'
    Run-Cmd 'py site_audit.py quality --help'
    Run-Cmd 'py site_audit.py playwright --help'
    Run-Cmd 'py site_audit.py run --help'
    Run-Cmd 'py site_audit.py diff --help'
}

function Test-SmokeCore {
    Ensure-Dirs
    Write-Step "Running smoke core commands"
    Run-Cmd "py site_audit.py crawl $Site --max-pages $MaxPages --out runs\crawl_test"
    Run-Cmd "py site_audit.py quality $Site --max-pages $MaxPages --out runs\quality_test"
    Run-Cmd "py site_audit.py playwright $Site --max-pages $PlaywrightPages --out runs\playwright_test"
    Run-Cmd "py site_audit.py run $Site --max-pages $MaxPages --skip-playwright --out runs\run_test"
    Run-Cmd "py site_audit.py run $Site --max-pages $MaxPages --out runs\run_full_test"
}

function Test-ResumeChecks {
    Ensure-Dirs
    Write-Step "Running resume/cache checks"
    Run-Cmd "py site_audit.py run $Site --max-pages $MaxPages --skip-playwright --out runs\resume_test"
    Run-Cmd "py site_audit.py run $Site --max-pages $MaxPages --skip-playwright --resume --out runs\resume_test"
    Run-Cmd "py site_audit.py crawl $Site --max-pages $MaxPages --resume --out runs\crawl_resume_test"
    Run-Cmd "py site_audit.py quality $Site --max-pages $MaxPages --resume --out runs\quality_resume_test"
    Run-Cmd "py site_audit.py playwright $Site --max-pages $PlaywrightPages --resume --out runs\playwright_resume_test"
}

function Test-DuplicateChecks {
    Ensure-Dirs
    Write-Step "Running duplicate/B3 checks"
    Run-Cmd "py site_audit.py run $Site --max-pages 10 --skip-playwright --out runs\dup_test"
    Run-Cmd 'powershell -NoProfile -Command "Select-String -Path runs\dup_test\run.json -Pattern ''\"duplicates\"''"'
    Run-Cmd 'powershell -NoProfile -Command "Select-String -Path runs\dup_test\run.json -Pattern ''\"validation\"''"'
    Run-Cmd 'powershell -NoProfile -Command "Select-String -Path runs\dup_test\run.json -Pattern ''\"confidence_bucket\"''"'
}

function Test-DiffChecks {
    Ensure-Dirs
    Write-Step "Running diff checks"
    Run-Cmd "py site_audit.py run $Site --max-pages $MaxPages --skip-playwright --out runs\golden"
    Run-Cmd "py site_audit.py run $Site --max-pages $MaxPages --skip-playwright --out runs\candidate"
    Run-Cmd 'py site_audit.py diff runs\golden runs\candidate --out diffs\golden_vs_candidate'
    Run-Cmd 'py site_audit.py diff runs\golden\run.json runs\candidate\run.json --out diffs\json_vs_json'
}

function Test-ErrorChecks {
    Ensure-Dirs
    Write-Step "Running error-handling checks"
    New-Item -ItemType Directory -Force -Path "runs\empty_test" | Out-Null

    Write-Host "These commands are expected to fail with a human-readable error." -ForegroundColor Yellow

    & py site_audit.py diff runs\does_not_exist runs\candidate --out diffs\bad_left
    & py site_audit.py diff runs\candidate runs\does_not_exist --out diffs\bad_right
    & py site_audit.py diff runs\empty_test runs\candidate --out diffs\bad_empty
}

function Test-BudgetChecks {
    Ensure-Dirs
    Write-Step "Running quality budget checks"
    Run-Cmd "py site_audit.py quality $Site --max-pages $MaxPages --out runs\quality_budget --budget-p90 0.8 --budget-lcp-ms 2500 --budget-cls 0.1 --budget-tbt-ms 300"
    Run-Cmd "py site_audit.py quality $Site --max-pages 10 --lh-mode sample --sample-total 3 --out runs\quality_sample"
    Run-Cmd "py site_audit.py quality $Site --max-pages 10 --lh-mode clustered --per-group 1 --out runs\quality_clustered"
}

function Test-OutputChecks {
    Ensure-Dirs
    Write-Step "Running output file/content checks"
    if (-not (Test-Path "runs\run_test\run.json")) {
        Run-Cmd "py site_audit.py run $Site --max-pages $MaxPages --skip-playwright --out runs\run_test"
    }
    if (-not (Test-Path "runs\golden\run.json")) {
        Run-Cmd "py site_audit.py run $Site --max-pages $MaxPages --skip-playwright --out runs\golden"
    }
    if (-not (Test-Path "runs\candidate\run.json")) {
        Run-Cmd "py site_audit.py run $Site --max-pages $MaxPages --skip-playwright --out runs\candidate"
    }
    if (-not (Test-Path "diffs\golden_vs_candidate\diff.json")) {
        Run-Cmd 'py site_audit.py diff runs\golden runs\candidate --out diffs\golden_vs_candidate'
    }

    Run-Cmd 'powershell -NoProfile -Command "Get-ChildItem runs\run_test"'
    Run-Cmd 'powershell -NoProfile -Command "Get-ChildItem diffs\golden_vs_candidate"'
    Run-Cmd 'powershell -NoProfile -Command "Test-Path runs\run_test\run.json"'
    Run-Cmd 'powershell -NoProfile -Command "Test-Path runs\run_test\run.md"'
    Run-Cmd 'powershell -NoProfile -Command "Test-Path diffs\golden_vs_candidate\diff.json"'
    Run-Cmd 'powershell -NoProfile -Command "Test-Path diffs\golden_vs_candidate\diff.md"'

    Run-Cmd 'powershell -NoProfile -Command "Select-String -Path runs\run_test\run.json -Pattern ''\"target_url\"''"'
    Run-Cmd 'powershell -NoProfile -Command "Select-String -Path runs\run_test\run.json -Pattern ''\"crawl\"''"'
    Run-Cmd 'powershell -NoProfile -Command "Select-String -Path runs\run_test\run.json -Pattern ''\"quality\"''"'
    Run-Cmd 'powershell -NoProfile -Command "Select-String -Path runs\run_test\run.json -Pattern ''\"timings\"''"'
    Run-Cmd 'powershell -NoProfile -Command "Select-String -Path runs\run_test\run.json -Pattern ''\"duplicates\"''"'
    Run-Cmd 'powershell -NoProfile -Command "Select-String -Path diffs\golden_vs_candidate\diff.json -Pattern ''\"summary\"''"'
}

function Test-RegressionPack {
    Write-Step "Running regression pack"
    Test-PytestQuick
    Test-PytestVerbose
    $oldLoops = $PytestLoops
    $script:PytestLoops = 3
    Test-PytestLoop
    $script:PytestLoops = $oldLoops
    Test-SmokeCore
    Test-DiffChecks
}

if ($All) {
    $Setup = $true
    $PytestQuick = $true
    $PytestVerbose = $true
    $PytestLoop = $true
    $HelpChecks = $true
    $SmokeCore = $true
    $ResumeChecks = $true
    $DuplicateChecks = $true
    $DiffChecks = $true
    $ErrorChecks = $true
    $BudgetChecks = $true
    $OutputChecks = $true
}

if (-not ($Setup -or $PytestQuick -or $PytestVerbose -or $PytestLoop -or $HelpChecks -or $SmokeCore -or $ResumeChecks -or $DuplicateChecks -or $DiffChecks -or $ErrorChecks -or $BudgetChecks -or $OutputChecks -or $RegressionPack -or $All)) {
    Write-Host "No switches provided. Example usage:" -ForegroundColor Yellow
    Write-Host "  .\run_tests.ps1 -PytestQuick"
    Write-Host "  .\run_tests.ps1 -SmokeCore -DiffChecks"
    Write-Host "  .\run_tests.ps1 -All"
    exit 0
}

if ($Setup) { Test-Setup }
if ($PytestQuick) { Test-PytestQuick }
if ($PytestVerbose) { Test-PytestVerbose }
if ($PytestLoop) { Test-PytestLoop }
if ($HelpChecks) { Test-HelpChecks }
if ($SmokeCore) { Test-SmokeCore }
if ($ResumeChecks) { Test-ResumeChecks }
if ($DuplicateChecks) { Test-DuplicateChecks }
if ($DiffChecks) { Test-DiffChecks }
if ($ErrorChecks) { Test-ErrorChecks }
if ($BudgetChecks) { Test-BudgetChecks }
if ($OutputChecks) { Test-OutputChecks }
if ($RegressionPack) { Test-RegressionPack }

Write-Host ""
Write-Host "Done." -ForegroundColor Green
