.PHONY: help format lint test coverage qa ci install-dev hooks

# Use project venv tools if available; otherwise fall back to system
RUFF := $(shell if [ -x ./.venv/bin/ruff ]; then echo ./.venv/bin/ruff; else echo ruff; fi)
PYTHON := $(shell if [ -x ./.venv/bin/python ]; then echo ./.venv/bin/python; else echo python; fi)
PIP := $(PYTHON) -m pip
PRECOMMIT := $(shell if [ -x ./.venv/bin/pre-commit ]; then echo ./.venv/bin/pre-commit; else echo pre-commit; fi)

.PHONY: help format lint test test-functional coverage qa qa-full ci install-dev hooks

help:
	@echo "Available make targets:"
	@echo ""
	@echo "  make format           - Format code using Ruff"
	@echo "  make lint             - Check code with Ruff linter"
	@echo "  make test             - Run pytest (excludes functional tests)"
	@echo "  make test-functional  - Run functional tests only"
	@echo "  make coverage         - Run tests with coverage report"
	@echo "  make qa               - Quick QA: format + lint + test"
	@echo "  make qa-full          - Full QA: format + lint + test + functional"
	@echo "  make ci               - CI pipeline: lint + test + pre-commit"
	@echo "  make install-dev      - Install development dependencies"
	@echo "  make hooks            - Install pre-commit git hooks"
	@echo "  make help             - Show this help message"
	@echo ""

format:
	$(RUFF) format .

lint:
	$(RUFF) check .

test:
	pytest -v --ignore=test_functional.py

test-functional:
	pytest test_functional.py -v --tb=short

coverage:
	pytest -v --cov=. --cov-report=term-missing:skip-covered --cov-report=html --cov-fail-under=80 --ignore=test_functional.py

.PHONY: coverage-all
coverage-all:
	pytest -v --cov=. --cov-report=term-missing:skip-covered --cov-report=html --cov-fail-under=80
qa: format lint test

qa-full: format lint test test-functional

ci: lint test
	$(PRECOMMIT) run --all-files --show-diff-on-failure
	$(PYTHON) -m pytest -q

install-dev:
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	$(PIP) install ruff pre-commit pytest-cov

hooks:
	pre-commit install
	pre-commit install --hook-type pre-push
