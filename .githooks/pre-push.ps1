# Pre-push hook for SinricPro Home Assistant Integration (PowerShell version)
# Runs ruff, mypy, and tests before allowing push

Write-Host "Running pre-push checks..." -ForegroundColor Cyan
Write-Host ""

$checksFailed = $false

# Check 1: Ruff format
Write-Host "Checking code formatting with ruff..." -ForegroundColor Yellow
$null = ruff format --check . 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "Code formatting check passed" -ForegroundColor Green
} else {
    Write-Host "Code formatting check failed" -ForegroundColor Red
    Write-Host "  Run: ruff format ." -ForegroundColor Gray
    $checksFailed = $true
}
Write-Host ""

# Check 2: Ruff lint
Write-Host "Running ruff linter..." -ForegroundColor Yellow
$null = ruff check . 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "Ruff linting passed" -ForegroundColor Green
} else {
    Write-Host "Ruff linting failed" -ForegroundColor Red
    Write-Host "  Run: ruff check . --fix" -ForegroundColor Gray
    $checksFailed = $true
}
Write-Host ""

# Check 3: MyPy type checking
Write-Host "Running mypy type checking..." -ForegroundColor Yellow
$null = mypy custom_components/sinricpro 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "MyPy type checking passed" -ForegroundColor Green
} else {
    Write-Host "MyPy type checking failed" -ForegroundColor Red
    Write-Host "  Run: mypy custom_components/sinricpro" -ForegroundColor Gray
    $checksFailed = $true
}
Write-Host ""

# Check 4: Tests
Write-Host "Running tests..." -ForegroundColor Yellow
$null = pytest tests/ -q 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "All tests passed" -ForegroundColor Green
} else {
    Write-Host "Tests failed" -ForegroundColor Red
    Write-Host "  Run: pytest tests/ -v" -ForegroundColor Gray
    $checksFailed = $true
}
Write-Host ""

# Final result
if ($checksFailed) {
    Write-Host "Pre-push checks failed. Please fix the issues before pushing." -ForegroundColor Red
    Write-Host ""
    Write-Host "To skip this hook (not recommended), use:" -NoNewline
    Write-Host " git push --no-verify"
    exit 1
} else {
    Write-Host "All pre-push checks passed! Proceeding with push..." -ForegroundColor Green
    exit 0
}
