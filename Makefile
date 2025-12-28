.PHONY: install test start lint clean

install:
	./scripts/install_hooks.sh
	python3 -m venv venv && . venv/bin/activate && pip install -r requirements.txt

test:
	. venv/bin/activate && pytest

start:
	./start.sh

lint:
	. venv/bin/activate && flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics

clean:
	rm -rf venv __pycache__ .pytest_cache
