.PHONY: install run test test-unit test-integration lint schema clean

# ── Setup ──────────────────────────────────────────────────────────────────────
install:
	python -m venv .venv
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install -r requirements.txt
	@echo "✅  Installed. Activate with: source .venv/bin/activate"

# ── Run pipeline ───────────────────────────────────────────────────────────────
run:
	bash scripts/run_pipeline.sh

# ── Schema ────────────────────────────────────────────────────────────────────
schema:
	bash scripts/apply_schema.sh

# ── Tests ─────────────────────────────────────────────────────────────────────
test:
	pytest tests/ -m "not integration"

test-unit:
	pytest tests/unit/ -v

test-integration:
	pytest tests/integration/ -v -m integration

# ── Lint ──────────────────────────────────────────────────────────────────────
lint:
	python -m py_compile app/**/*.py
	@echo "✅  Syntax OK"

# ── Clean ─────────────────────────────────────────────────────────────────────
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete
	rm -rf .pytest_cache .coverage htmlcov
	@echo "✅  Cleaned"
