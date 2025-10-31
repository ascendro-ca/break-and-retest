.PHONY: format lint test qa ci install-dev hooks

# Use project venv tools if available; otherwise fall back to system
RUFF := $(shell if [ -x ./.venv/bin/ruff ]; then echo ./.venv/bin/ruff; else echo ruff; fi)
PYTHON := $(shell if [ -x ./.venv/bin/python ]; then echo ./.venv/bin/python; else echo python; fi)
PIP := $(PYTHON) -m pip
PRECOMMIT := $(shell if [ -x ./.venv/bin/pre-commit ]; then echo ./.venv/bin/pre-commit; else echo pre-commit; fi)

format:
	$(RUFF) format .

lint:
	$(RUFF) check .

test:
	$(PYTHON) -m pytest -q

qa: format lint test

ci: install-dev
	$(PRECOMMIT) run --all-files --show-diff-on-failure
	$(PYTHON) -m pytest -q

install-dev:
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	$(PIP) install ruff pre-commit

hooks:
	pre-commit install
	pre-commit install --hook-type pre-push
