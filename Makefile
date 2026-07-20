.PHONY: install api test test-api evaluate error-analysis tune-thresholds ingest ingest-dry-run rebuild-embeddings clean-embeddings clean help

install:
	python3 -m pip install -r requirements.txt

api:
	python3 -m uvicorn app.main:app --reload

test:
	python3 -m pytest tests -q

test-api:
	python3 scripts/test_api.py

evaluate:
	python3 layer1_evaluate.py

error-analysis:
	python3 layer1_error_analysis.py

tune-thresholds:
	python3 layer1_threshold_tuning.py

ingest:
	python3 scripts/ingest_evidence.py

ingest-dry-run:
	python3 scripts/ingest_evidence.py --dry-run

rebuild-embeddings:
	python3 scripts/rebuild_embeddings.py

clean-embeddings:
	rm -rf data/cache
	@echo "Embedding cache removed."
	@echo "Run 'make rebuild-embeddings' or start the API to rebuild it."

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

help:
	@echo "Available commands:"
	@echo "  make install              Install dependencies"
	@echo "  make api                  Start the FastAPI development server"
	@echo "  make test                 Run all pytest tests"
	@echo "  make test-api             Run the API smoke test"
	@echo "  make evaluate             Run evaluation"
	@echo "  make error-analysis       Run error analysis"
	@echo "  make tune-thresholds      Run threshold tuning"
	@echo "  make ingest               Build data/evidence.csv from JSONL"
	@echo "  make ingest-dry-run       Validate evidence without writing CSV"
	@echo "  make rebuild-embeddings   Force a safe embedding-cache rebuild"
	@echo "  make clean-embeddings     Remove generated embedding cache"
	@echo "  make clean                Remove Python cache files"
