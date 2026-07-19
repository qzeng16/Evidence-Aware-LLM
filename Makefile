.PHONY: install api test test-api evaluate error-analysis tune-thresholds clean help

install:
	pip install -r requirements.txt

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

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

help:
	@echo "Available commands:"
	@echo "  make install           Install dependencies"
	@echo "  make api               Start FastAPI server"
	@echo "  make test              Run pytest core tests"
	@echo "  make test-api          Run API smoke tests"
	@echo "  make evaluate          Run evaluation"
	@echo "  make error-analysis    Run error analysis"
	@echo "  make tune-thresholds   Run threshold tuning"
	@echo "  make clean             Remove Python cache files"
