# ── Settings ──────────────────────────────────────────────────
# Python interpreter inside the project virtual environment (Linux/macOS path)
PYTHON ?= .venv/bin/python

# Targets below are commands, not files
.PHONY: install lint test local-run check-hygiene deploy teardown

# ── Local targets (working) ───────────────────────────────────
# Install the package and dev tools into the virtual environment
install:
	$(PYTHON) -m pip install -e ".[dev]"

# Lint all Python code
lint:
	$(PYTHON) -m ruff check src tests

# Run the test suite
test:
	$(PYTHON) -m pytest -v

# Run the whole pipeline locally from the UCI file into output/local
local-run:
	$(PYTHON) -m clickstream.local_run --source "data/e-shop clothing 2008.csv" --output output/local

# Fail if any local-only file is tracked by git
check-hygiene:
	@if git ls-files | grep -E '(^|/)(\.env|CLAUDE\.md|workflow_status[^/]*\.md)$$'; then echo "Local-only file is tracked"; exit 1; fi

# ── Cloud targets (not built yet) ─────────────────────────────
# Cloud deploy arrives with tier T1 (see docs/adr/0001-hybrid-cost-tiers.md)
deploy:
	@echo "Not built yet: cloud tiers start at T1 (ADR-0001 annex)"; exit 1

# Cloud teardown arrives with tier T1
teardown:
	@echo "Not built yet: nothing is deployed"; exit 1
