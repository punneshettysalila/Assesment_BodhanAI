.PHONY: install test check demo
install:
	pip install -e ".[dev]"
test:
	pytest -q
check: test            # guard test (no foreign models) runs as part of the suite
	python -m bodhan_lesson --help >/dev/null
demo:
	python -m bodhan_lesson --input scans/chapter.pdf --langs hi,ta,bn --out out/demo -v
