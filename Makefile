.PHONY: help install run test lint clean eval ingest ingest-list docker-build docker-up docker-down

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install dependencies
	pip install -r requirements.txt

run: ## Start API server (with hot reload)
	python -m apps.api.main

test: ## Run all tests
	pytest tests/ -q --tb=short

test-v: ## Run all tests (verbose)
	pytest tests/ -v --tb=short

lint: ## Run ruff linter
	ruff check . --ignore=E501,E402,F841,F811 --exclude=.git,__pycache__,.pytest_cache,venv,.venv,knowledge_pack

lint-fix: ## Auto-fix lint issues
	ruff check . --fix --ignore=E501,E402,F841,F811 --exclude=.git,__pycache__,.pytest_cache,venv,.venv,knowledge_pack

ingest: ## Bootstrap dev samples and ingest all documents
	python3 scripts/ingest_documents.py --bootstrap-samples
	python3 scripts/ingest_documents.py --all

ingest-list: ## Show document ingest status
	python3 scripts/ingest_documents.py --list

eval: ## Run batch evaluation
	python -c "
from runtime.agents.orchestrator import MultiAgentEngine
from evaluation.runner.runner import EvalRunner
from evaluation.datasets.samples import EVAL_DATASET
engine = MultiAgentEngine()
runner = EvalRunner(engine)
result = runner.run_batch(EVAL_DATASET, verbose=True)
print(f'\nAvg score: {result.avg_score}')
print(f'Passed: {result.passed}/{result.total_samples}')
"

clean: ## Clean cache files
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete 2>/dev/null || true
	rm -rf .pytest_cache

docker-build: ## Build Docker image
	docker compose build

docker-up: ## Start services with Docker
	docker compose up -d

docker-down: ## Stop Docker services
	docker compose down
