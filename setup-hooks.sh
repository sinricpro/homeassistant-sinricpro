#!/bin/bash

# Setup script to install git hooks for SinricPro integration

echo "🔧 Setting up git hooks..."

# Configure git to use .githooks directory
git config core.hooksPath .githooks

# Make hooks executable
chmod +x .githooks/pre-push

echo "✅ Git hooks installed successfully!"
echo ""
echo "The pre-push hook will now run automatically before each push."
echo "It will check:"
echo "  - Code formatting (ruff format)"
echo "  - Linting (ruff check)"
echo "  - Type checking (mypy)"
echo "  - Tests (pytest)"
echo ""
echo "To skip the hook (not recommended), use: git push --no-verify"
