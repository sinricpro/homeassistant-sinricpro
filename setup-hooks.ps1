# Setup script to install git hooks for SinricPro integration (PowerShell version)

Write-Host "Setting up git hooks..." -ForegroundColor Cyan

# Configure git to use .githooks directory
git config core.hooksPath .githooks

Write-Host "Git hooks installed successfully!" -ForegroundColor Green
Write-Host ""
Write-Host "The pre-push hook will now run automatically before each push."
Write-Host "It will check:"
Write-Host "  - Code formatting (ruff format)"
Write-Host "  - Linting (ruff check)"
Write-Host "  - Type checking (mypy)"
Write-Host "  - Tests (pytest)"
Write-Host ""
Write-Host "To skip the hook (not recommended), use:" -NoNewline
Write-Host " git push --no-verify"
