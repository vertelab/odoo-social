# Vertel odoo-social — developer entry points.
#
# The p-file sync check is the important one. Run it before committing, or
# install the git hook once per clone with `make install-hooks`.

SHELL := /bin/bash
REPO_ROOT := $(shell git rev-parse --show-toplevel)
CHECKER := $(REPO_ROOT)/scripts/check_pfile_sync.py

.PHONY: help check-pfiles check-pfiles-pairs install-hooks

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

check-pfiles: ## Fail if a p-file and its generated branch file have diverged
	@python3 $(CHECKER)

check-pfiles-pairs: ## List every p-file pair and its sync state
	@python3 $(CHECKER) --pairs

install-hooks: ## Install the pre-commit p-file guard into .git/hooks
	@$(REPO_ROOT)/scripts/install_hooks.sh
