PYTHON ?= python

.PHONY: install dev init demo run check test translations clean

install:
	$(PYTHON) -m pip install -r requirements.txt

dev:
	$(PYTHON) -m pip install -r requirements-dev.txt

init:
	CARELOG_START_SCHEDULER=0 $(PYTHON) -m flask --app app init-db

demo:
	CARELOG_START_SCHEDULER=0 $(PYTHON) -m flask --app app seed-demo

run:
	$(PYTHON) app.py

translations:
	$(PYTHON) scripts/check_translations.py

test:
	$(PYTHON) -m pytest

check:
	$(PYTHON) -m compileall -q .
	$(PYTHON) scripts/check_translations.py
	$(PYTHON) scripts/static_check.py
	$(PYTHON) -m pytest

clean:
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -rf .pytest_cache htmlcov .coverage coverage.xml
