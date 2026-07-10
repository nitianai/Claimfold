.PHONY: ci test install-hooks

ci:
	./scripts/ci.sh

test:
	python3 tests/run_tests.py

install-hooks:
	./scripts/install-git-hooks.sh