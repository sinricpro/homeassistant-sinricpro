# Git Hooks

This directory contains git hooks to ensure code quality before pushing.

## Pre-Push Hook

The pre-push hook runs automatically before each `git push` and checks:

1. **Code Formatting** - Ensures code is formatted with `ruff format`
2. **Linting** - Checks for code quality issues with `ruff check`
3. **Type Checking** - Validates types with `mypy`
4. **Tests** - Runs the full test suite with `pytest`

## Installation

### Linux / macOS / WSL

```bash
./setup-hooks.sh
```

### Windows (PowerShell)

```powershell
.\setup-hooks.ps1
```

### Manual Installation

```bash
git config core.hooksPath .githooks
chmod +x .githooks/pre-push
```

## Usage

Once installed, the hook runs automatically before every push:

```bash
git push
```

**Output example:**
```
🔍 Running pre-push checks...

📝 Checking code formatting with ruff...
✓ Code formatting check passed

🔎 Running ruff linter...
✓ Ruff linting passed

🔬 Running mypy type checking...
✓ MyPy type checking passed

🧪 Running tests...
✓ All tests passed

✅ All pre-push checks passed! Proceeding with push...
```

## Skipping the Hook

**Not recommended**, but you can skip the hook with:

```bash
git push --no-verify
```

## Troubleshooting

### Hook not running on Windows

Make sure you're using the PowerShell script:
```powershell
powershell.exe -ExecutionPolicy Bypass -File .githooks/pre-push.ps1
```

### Checks failing

Run the individual commands to see detailed errors:

```bash
# Check formatting
ruff format --check .

# Check linting
ruff check .

# Check types
mypy custom_components/sinricpro

# Run tests
pytest tests/ -v
```

### Fix issues automatically

```bash
# Auto-fix formatting
ruff format .

# Auto-fix some linting issues
ruff check . --fix
```
