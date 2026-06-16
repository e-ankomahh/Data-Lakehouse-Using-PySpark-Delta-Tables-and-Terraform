.PHONY: install lint format test test-unit test-integration coverage local-run clean help

PYTHON := python
PIP    := pip
PYTEST := pytest
SRC    := src tests config

help:
	@echo "Available targets:"
	@echo "  install          Install dev dependencies"
	@echo "  lint             Run ruff + black check (no auto-fix)"
	@echo "  format           Auto-fix with ruff + black"
	@echo "  test             Run all tests with coverage"
	@echo "  test-unit        Run unit tests only"
	@echo "  test-integration Run integration tests only (requires moto)"
	@echo "  coverage         Generate HTML coverage report"
	@echo "  local-run        Run full pipeline locally in PySpark local mode"
	@echo "  clean            Remove build artifacts and cache"

install:
	$(PIP) install -r requirements-dev.txt
	pre-commit install

lint:
	ruff check $(SRC)
	black --check $(SRC)

format:
	ruff check --fix $(SRC)
	black $(SRC)

test:
	$(PYTEST) tests/ --cov=src --cov-report=term-missing --cov-fail-under=80

test-unit:
	$(PYTEST) tests/unit/ -m unit -v

test-integration:
	$(PYTEST) tests/integration/ -m integration -v

coverage:
	$(PYTEST) tests/ --cov=src --cov-report=html
	@echo "Coverage report: htmlcov/index.html"

local-run:
	bash scripts/run_local_pipeline.sh

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name htmlcov -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name dist -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	@echo "Clean complete."
