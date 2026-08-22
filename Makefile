PYTHON ?= python

.PHONY: install dev init upgrade demo run check test translations media-preview media-migrate rebuild-abnormal clean

install:
	$(PYTHON) -m pip install -r requirements.txt

dev:
	$(PYTHON) -m pip install -r requirements-dev.txt

init:
	CARELOG_START_SCHEDULER=0 $(PYTHON) -m flask --app app init-db

upgrade:
	CARELOG_START_SCHEDULER=0 $(PYTHON) -m flask --app app upgrade-db

demo:
	CARELOG_START_SCHEDULER=0 $(PYTHON) -m flask --app app seed-demo

run:
	$(PYTHON) app.py

translations:
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) scripts/check_translations.py

media-preview:
	CARELOG_START_SCHEDULER=0 $(PYTHON) -m flask --app app media-migrate --dry-run

media-migrate:
	CARELOG_START_SCHEDULER=0 $(PYTHON) -m flask --app app media-migrate --apply

rebuild-abnormal:
	CARELOG_START_SCHEDULER=0 $(PYTHON) -m flask --app app rebuild-abnormal-events

test:
	$(PYTHON) -m pytest

check:
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m compileall -q .
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) scripts/check_translations.py
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) scripts/static_check.py
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m pytest

clean:
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type f -name '*.pyc' -delete
	rm -rf .pytest_cache htmlcov .coverage coverage.xml
