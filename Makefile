.PHONY: ci test test-app test-platform install install-hooks

ci:
	./scripts/ci.sh

install:
	./scripts/install_editable.sh

test:
	python3 tests/platform/run_tests.py
	python3 tests/app/run_tests.py

test-app:
	python3 tests/app/run_tests.py

test-platform:
	./scripts/check_platform_boundary.sh
	python3 tests/platform/run_tests.py

install-hooks:
	./scripts/install-git-hooks.sh