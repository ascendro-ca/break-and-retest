.PHONY: format lint test qa install-dev hooks

# Use project venv tools if available; otherwise fall back to system
RUFF := $(shell if [ -x ./.venv/bin/ruff ]; then echo ./.venv/bin/ruff; else echo ruff; fi)
PYTHON := $(shell if [ -x ./.venv/bin/python ]; then echo ./.venv/bin/python; else echo python; fi)
PIP := $(PYTHON) -m pip

format:
	$(RUFF) format .

lint:
	$(RUFF) check .

test:
	$(PYTHON) -m pytest -q

qa: format lint test

install-dev:
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	$(PIP) install ruff pre-commit

hooks:
	pre-commit install
	pre-commit install --hook-type pre-push
