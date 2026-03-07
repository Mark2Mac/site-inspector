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
    [int]$PytestLoops = 5,

    [string]$RootDir = ".site_inspector_local"
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

function Join-Root([string]$child) {
    return [System.IO.Path]::Combine($RootDir, $child)
}

function Ensure-Dirs {
    New-Item -ItemType Directory -Force -Path $RootDir | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Root "runs") | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Root "diffs") | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Root "logs") | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Root "budgets") | Out-Null
}

function Expect-NativeFailure([string]$label, [scriptblock]$block) {
    Write-Host "PS> $label" -ForegroundColor DarkGray
    try {
        & $block 2>$null
    } catch {
        # Ignore stderr noise from commands that are expected to fail.
    }
    if ($LASTEXITCODE -eq 0) {
        throw ("Command unexpectedly succeeded: {0}" -f $label)
    }
    Write-Host ("Expected failure observed (exit {0})" -f $LASTEXITCODE) -ForegroundColor Yellow
}

function Write-LooseBudget {
    Ensure-Dirs
    $budgetPath = Join-Root "budgets\loose_budget.json"
    $budgetObj = @{
        categories = @{
            performance      = @{ min_score = 0.00 }
            seo              = @{ min_score = 0.00 }
            accessibility    = @{ min_score = 0.00 }
            "best-practices" = @{ min_score = 0.00 }
        }
        audits = @{}
    }

    $json = $budgetObj | ConvertTo-Json -Depth 5
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($budgetPath, $json, $utf8NoBom)
    return $budgetPath
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
        Write-Host ("Loop {0} / {1}" -f $i, $PytestLoops) -ForegroundColor Yellow
        Run-Cmd 'py -m pytest -q'
    }
}

function Test-HelpChecks {
    Write-Step "Checking CLI help"
    Run-Cmd 'py site_audit.py --help'
    Run-Cmd 'py site_audit.py --version'
    Run-Cmd 'py -m site_inspector --version'
    Run-Cmd 'py -m site_inspector --help'
    Run-Cmd 'py site_audit.py crawl --help'
    Run-Cmd 'py site_audit.py quality --help'
    Run-Cmd 'py site_audit.py playwright --help'
    Run-Cmd 'py site_audit.py run --help'
    Run-Cmd 'py site_audit.py diff --help'
}

function Test-SmokeCore {
    Ensure-Dirs
    Write-Step "Running smoke core commands"
    Run-Cmd ('py site_audit.py crawl "{0}" --max-pages {1} --out "{2}"' -f $Site, $MaxPages, (Join-Root "runs\crawl_test"))
    Run-Cmd ('py site_audit.py quality "{0}" --max-pages {1} --out "{2}"' -f $Site, $MaxPages, (Join-Root "runs\quality_test"))
    Run-Cmd ('py site_audit.py playwright "{0}" --max-pages {1} --out "{2}"' -f $Site, $PlaywrightPages, (Join-Root "runs\playwright_test"))
    Run-Cmd ('py site_audit.py run "{0}" --max-pages {1} --skip-playwright --out "{2}"' -f $Site, $MaxPages, (Join-Root "runs\run_test"))
    Run-Cmd ('py site_audit.py run "{0}" --max-pages {1} --out "{2}"' -f $Site, $MaxPages, (Join-Root "runs\run_full_test"))
}

function Test-ResumeChecks {
    Ensure-Dirs
    Write-Step "Running resume/cache checks"
    Run-Cmd ('py site_audit.py run "{0}" --max-pages {1} --skip-playwright --out "{2}"' -f $Site, $MaxPages, (Join-Root "runs\resume_test"))
    Run-Cmd ('py site_audit.py run "{0}" --max-pages {1} --skip-playwright --resume --out "{2}"' -f $Site, $MaxPages, (Join-Root "runs\resume_test"))
    Run-Cmd ('py site_audit.py crawl "{0}" --max-pages {1} --resume --out "{2}"' -f $Site, $MaxPages, (Join-Root "runs\crawl_resume_test"))
    Run-Cmd ('py site_audit.py quality "{0}" --max-pages {1} --resume --out "{2}"' -f $Site, $MaxPages, (Join-Root "runs\quality_resume_test"))
    Run-Cmd ('py site_audit.py playwright "{0}" --max-pages {1} --resume --out "{2}"' -f $Site, $PlaywrightPages, (Join-Root "runs\playwright_resume_test"))
}

function Test-DuplicateChecks {
    Ensure-Dirs
    Write-Step "Running duplicate/B3 checks"
    $dupRun = Join-Root "runs\dup_test"
    Run-Cmd ('py site_audit.py run "{0}" --max-pages 10 --skip-playwright --out "{1}"' -f $Site, $dupRun)

    $jsonPath = Join-Root "runs\dup_test\run.json"
    $json = Get-Content -Raw -Path $jsonPath | ConvertFrom-Json

    if (-not $json.PSObject.Properties.Name.Contains("duplicates")) {
        throw ("duplicates block missing in {0}" -f $jsonPath)
    }
    if (-not $json.duplicates.PSObject.Properties.Name.Contains("validation")) {
        throw ("duplicates.validation block missing in {0}" -f $jsonPath)
    }

    Write-Host "duplicates block present" -ForegroundColor Green
    Write-Host "validation block present" -ForegroundColor Green
}

function Test-DiffChecks {
    Ensure-Dirs
    Write-Step "Running diff checks"
    $golden = Join-Root "runs\golden"
    $candidate = Join-Root "runs\candidate"
    $diffDir = Join-Root "diffs\golden_vs_candidate"
    $diffJsonDir = Join-Root "diffs\json_vs_json"

    Run-Cmd ('py site_audit.py run "{0}" --max-pages {1} --skip-playwright --out "{2}"' -f $Site, $MaxPages, $golden)
    Run-Cmd ('py site_audit.py run "{0}" --max-pages {1} --skip-playwright --out "{2}"' -f $Site, $MaxPages, $candidate)
    Run-Cmd ('py site_audit.py diff "{0}" "{1}" --out "{2}"' -f $golden, $candidate, $diffDir)
    Run-Cmd ('py site_audit.py diff "{0}" "{1}" --out "{2}"' -f (Join-Root "runs\golden\run.json"), (Join-Root "runs\candidate\run.json"), $diffJsonDir)
}

function Test-ErrorChecks {
    Ensure-Dirs
    Write-Step "Running error-handling checks"
    $candidate = Join-Root "runs\candidate"
    if (-not (Test-Path (Join-Root "runs\candidate\run.json"))) {
        Run-Cmd ('py site_audit.py run "{0}" --max-pages {1} --skip-playwright --out "{2}"' -f $Site, $MaxPages, $candidate)
    }

    New-Item -ItemType Directory -Force -Path (Join-Root "runs\empty_test") | Out-Null
    Write-Host "These commands are expected to fail with a human-readable error." -ForegroundColor Yellow

    Expect-NativeFailure ('py site_audit.py diff "{0}" "{1}" --out "{2}"' -f (Join-Root "runs\does_not_exist"), $candidate, (Join-Root "diffs\bad_left")) {
        py site_audit.py diff (Join-Root "runs\does_not_exist") $candidate --out (Join-Root "diffs\bad_left")
    }

    Expect-NativeFailure ('py site_audit.py diff "{0}" "{1}" --out "{2}"' -f $candidate, (Join-Root "runs\does_not_exist"), (Join-Root "diffs\bad_right")) {
        py site_audit.py diff $candidate (Join-Root "runs\does_not_exist") --out (Join-Root "diffs\bad_right")
    }

    Expect-NativeFailure ('py site_audit.py diff "{0}" "{1}" --out "{2}"' -f (Join-Root "runs\empty_test"), $candidate, (Join-Root "diffs\bad_empty")) {
        py site_audit.py diff (Join-Root "runs\empty_test") $candidate --out (Join-Root "diffs\bad_empty")
    }
}

function Test-BudgetChecks {
    Ensure-Dirs
    Write-Step "Running quality budget checks"
    $budgetPath = Write-LooseBudget
    Run-Cmd ('py site_audit.py quality "{0}" --max-pages {1} --budget "{2}" --out "{3}"' -f $Site, $MaxPages, $budgetPath, (Join-Root "runs\quality_budget"))
    Run-Cmd ('py site_audit.py quality "{0}" --max-pages 10 --lighthouse-sample 3 --out "{1}"' -f $Site, (Join-Root "runs\quality_sample"))
    Run-Cmd ('py site_audit.py quality "{0}" --max-pages 10 --lighthouse-sample 3 --lighthouse-per-group 1 --out "{1}"' -f $Site, (Join-Root "runs\quality_grouped"))
}

function Test-OutputChecks {
    Ensure-Dirs
    Write-Step "Running output file/content checks"
    $runTest = Join-Root "runs\run_test"
    $golden = Join-Root "runs\golden"
    $candidate = Join-Root "runs\candidate"
    $diffDir = Join-Root "diffs\golden_vs_candidate"

    $runJsonPath = Join-Root "runs\run_test\run.json"
    $runMdPath = Join-Root "runs\run_test\run.md"
    $diffJsonPath = Join-Root "diffs\golden_vs_candidate\diff.json"
    $diffMdPath = Join-Root "diffs\golden_vs_candidate\diff.md"
    $qualitySummaryPath = Join-Root "runs\quality_test\quality_summary.json"

    if (-not (Test-Path $runJsonPath)) {
        Run-Cmd ('py site_audit.py run "{0}" --max-pages {1} --skip-playwright --out "{2}"' -f $Site, $MaxPages, $runTest)
    }
    if (-not (Test-Path (Join-Root "runs\golden\run.json"))) {
        Run-Cmd ('py site_audit.py run "{0}" --max-pages {1} --skip-playwright --out "{2}"' -f $Site, $MaxPages, $golden)
    }
    if (-not (Test-Path (Join-Root "runs\candidate\run.json"))) {
        Run-Cmd ('py site_audit.py run "{0}" --max-pages {1} --skip-playwright --out "{2}"' -f $Site, $MaxPages, $candidate)
    }
    if (-not (Test-Path $diffJsonPath)) {
        Run-Cmd ('py site_audit.py diff "{0}" "{1}" --out "{2}"' -f $golden, $candidate, $diffDir)
    }
    if (-not (Test-Path $qualitySummaryPath)) {
        Run-Cmd ('py site_audit.py quality "{0}" --max-pages {1} --out "{2}"' -f $Site, $MaxPages, (Join-Root "runs\quality_test"))
    }

    Get-ChildItem $runTest | Out-Host
    Get-ChildItem $diffDir | Out-Host

    $runJson = Get-Content -Raw -Path $runJsonPath | ConvertFrom-Json
    $diffJson = Get-Content -Raw -Path $diffJsonPath | ConvertFrom-Json
    $qualitySummary = Get-Content -Raw -Path $qualitySummaryPath | ConvertFrom-Json
    $runMd = Get-Content -Raw -Path $runMdPath
    $diffMd = Get-Content -Raw -Path $diffMdPath

    foreach ($key in @("target_url", "crawl", "quality", "timings", "duplicates", "seo", "ai")) {
        if (-not $runJson.PSObject.Properties.Name.Contains($key)) {
            throw ("run.json missing key: {0}" -f $key)
        }
    }

    if (-not $diffJson.PSObject.Properties.Name.Contains("quality")) {
        throw "diff.json missing key: quality"
    }
    if (-not $diffJson.quality.PSObject.Properties.Name.Contains("summary")) {
        throw "diff.json missing key: quality.summary"
    }

    foreach ($key in @("generated_at", "pages_tested", "pages_failed", "passed", "budget", "lighthouse_workers", "results", "failures")) {
        if (-not $qualitySummary.PSObject.Properties.Name.Contains($key)) {
            throw ("quality_summary.json missing key: {0}" -f $key)
        }
    }

    foreach ($needle in @("Executive summary", "Priority findings", "Artifacts")) {
        if ($runMd -notmatch [Regex]::Escape($needle)) {
            throw ("run.md missing section: {0}" -f $needle)
        }
    }

    foreach ($needle in @("Executive summary")) {
        if ($diffMd -notmatch [Regex]::Escape($needle)) {
            throw ("diff.md missing section: {0}" -f $needle)
        }
    }

    Write-Host "run.json keys validated" -ForegroundColor Green
    Write-Host "diff.json keys validated" -ForegroundColor Green
    Write-Host "quality_summary.json keys validated" -ForegroundColor Green
    Write-Host "run.md sections validated" -ForegroundColor Green
    Write-Host "diff.md sections validated" -ForegroundColor Green
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
    Write-Host "  .\run_tests.ps1 -All -RootDir .site_inspector_local"
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
Write-Host ('Done. Local artifacts are under: {0}' -f $RootDir) -ForegroundColor Green
