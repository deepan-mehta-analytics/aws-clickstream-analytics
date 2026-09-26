# ── Settings ──────────────────────────────────────────────────
# Python interpreter inside the project virtual environment (Linux/macOS path)
PYTHON ?= .venv/bin/python

# cfn-lint inside the project virtual environment (Linux/macOS path)
CFN_LINT ?= .venv/bin/cfn-lint

# Targets below are commands, not files
.PHONY: install lint lint-infra test local-run check-hygiene deploy teardown

# ── Local targets (working) ───────────────────────────────────
# Install the package and dev tools into the virtual environment
install:
	$(PYTHON) -m pip install -e ".[dev]"

# Lint all Python code
lint:
	$(PYTHON) -m ruff check src tests

# Lint CloudFormation templates and run the template guardrail tests (no AWS credentials needed)
lint-infra:
	$(CFN_LINT)
	$(PYTHON) -m pytest -v tests/test_infra_templates.py

# Run the test suite
test:
	$(PYTHON) -m pytest -v

# Run the whole pipeline locally from the UCI file into output/local
local-run:
	$(PYTHON) -m clickstream.local_run --source "data/e-shop clothing 2008.csv" --output output/local

# Fail if any local-only file is tracked by git
check-hygiene:
	@if git ls-files | grep -E '(^|/)(\.env(\.[^/]*)?|CLAUDE\.md|workflow_status[^/]*\.md)$$' | grep -vE '(^|/)\.env\.example$$'; then echo "Local-only file is tracked"; exit 1; fi

# ── Cloud targets (owner-run only) ────────────────────────────
# Cloud deploy is owner-run only (ADR-0004)
deploy:
	@echo "Owner-run only: see infra/README.md (sam deploy with a reviewed change set)"; exit 1

# Cloud teardown is owner-run only (ADR-0004)
teardown:
	@echo "Owner-run only: see infra/README.md (sam delete, then log it in docs/cost-model.md)"; exit 1
