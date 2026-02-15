.PHONY: help install dev-install test lint format clean run-monitor run-server

help:
	@echo "Available commands:"
	@echo "  make install      - Install production dependencies"
	@echo "  make dev-install  - Install development dependencies"
	@echo "  make test         - Run tests with coverage"
	@echo "  make lint         - Run linters (flake8, mypy)"
	@echo "  make format       - Format code (black, isort)"
	@echo "  make clean        - Remove build artifacts and cache"
	@echo "  make run-monitor  - Start disc monitoring daemon"
	@echo "  make run-server   - Start web server"

install:
	pip install -e .

dev-install:
	pip install -e ".[dev,content]"

test:
	pytest

test-verbose:
	pytest -v -s

test-coverage:
	pytest --cov=src --cov-report=html --cov-report=term

lint:
	flake8 src tests
	mypy src

format:
	black src tests
	isort src tests

clean:
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info
	rm -rf .pytest_cache/
	rm -rf .coverage
	rm -rf htmlcov/
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete

run-monitor:
	python -m src.main --config config.json --mode monitor

run-server:
	python -m src.main --config config.json --mode server

run-full:
	python -m src.main --config config.json --mode full

setup:
	python scripts/setup.py
