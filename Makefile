.PHONY: format lint test coverage qa ci install-dev hooks

# Use project venv tools if available; otherwise fall back to system
RUFF := $(shell if [ -x ./.venv/bin/ruff ]; then echo ./.venv/bin/ruff; else echo ruff; fi)
PYTHON := $(shell if [ -x ./.venv/bin/python ]; then echo ./.venv/bin/python; else echo python; fi)
PIP := $(PYTHON) -m pip
PRECOMMIT := $(shell if [ -x ./.venv/bin/pre-commit ]; then echo ./.venv/bin/pre-commit; else echo pre-commit; fi)

.PHONY: format lint test test-functional coverage qa qa-full ci install-dev hooks

format:
	$(RUFF) format .

lint:
	$(RUFF) check .

test:
	pytest -v --ignore=test_functional.py

test-functional:
	pytest test_functional.py -v --tb=short

coverage:

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
