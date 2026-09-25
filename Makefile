# ──────────────────────────────────────────────────────────────────────────────
# Jolarca Control Plane — Makefile
# ──────────────────────────────────────────────────────────────────────────────

.PHONY: help setup validate compliance drift fleet-audit org-audit \
        init fmt fmt-check lint tf-validate py-lint py-type sh-lint yaml-lint \
        test plan apply list-repos count-repos clean

.DEFAULT_GOAL := help

# ── Help ─────────────────────────────────────────────────────────────────────
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-16s\033[0m %s\n", $$1, $$2}'

# ── Environment ──────────────────────────────────────────────────────────────
# Dependencies are PINNED (requirements*.txt) and the rule selection is PINNED
# (pyproject.toml). Both matter: ruff's default rule set changes between
# releases, so an unpinned ruff makes "lint passes" a moving target.
setup: ## Create .venv and install pinned runtime + dev dependencies
	python3 -m venv .venv
	.venv/bin/pip install -r requirements-dev.txt
	@echo "Activate with: . .venv/bin/activate"

# ── Validation (offline, no network, no state) ───────────────────────────────
validate: ## Validate all repo YAML definitions against policy
	python3 scripts/validate_repos.py

compliance: ## Run the full compliance report (JSON)
	python3 scripts/compliance_check.py

lint: fmt-check tf-validate validate py-lint py-type sh-lint yaml-lint test ## Everything CI runs before a plan

fmt: ## Format Terraform files in place
	terraform fmt -recursive

fmt-check: ## Fail if Terraform files are unformatted
	terraform fmt -check -recursive

tf-validate: ## terraform init (no backend) + validate
	terraform init -input=false -backend=false >/dev/null
	terraform validate

# ── Code standard (CONTRIBUTING.md; policy/compliance-gates.yml code_quality) ─
# These three targets ARE the code_quality gate for tier:governance. Before they
# existed, that gate named ruff / mypy --strict / shellcheck as mandatory and
# nothing anywhere ran them (D-27).
py-lint: ## ruff check over scripts/ and tests/ (rules pinned in pyproject.toml)
	ruff check scripts/ tests/

py-type: ## mypy --strict over scripts/ (config in pyproject.toml)
	mypy

sh-lint: ## shellcheck over every shell script
	shellcheck -x scripts/*.sh tests/*.sh

yaml-lint: ## yamllint over the repo (config: .yamllint; not --strict, see file)
	yamllint -c .yamllint .

test: ## Regression tests for the plan-safety gate (D-22)
	bash tests/test_check_plan_safety.sh

# ── Live checks (read-only, need gh / GITHUB_TOKEN) ──────────────────────────
drift: ## Diff the allow-list against the live jolarca-dev org
	python3 scripts/drift_detect.py

fleet-audit: ## ADR-0004 fleet separation guard (R1/R2/R3)
	bash scripts/check_fleet_separation.sh

org-audit: ## Capture the org-wide delivery chain into an evidence bundle
	bash scripts/org_delivery_audit.sh

# ── Terraform ────────────────────────────────────────────────────────────────
init: ## Initialize Terraform
	terraform init -input=false

plan: validate ## Run terraform plan — REFUSED until the state migration completes
	@echo "---------------------------------------------------------------"
	@echo "STOP. This root does not own the github_* state yet."
	@echo "The resources it declares are live in jolarca-infrastructure."
	@echo "Planning here is safe only with -refresh=false; applying is not"
	@echo "safe at all until docs/state-migration-runbook.md completes."
	@echo "---------------------------------------------------------------"
	@read -p "Run an offline plan (-refresh=false)? [y/N] " c && [ "$$c" = "y" ] || exit 1
	terraform plan -input=false -refresh=false -out=tfplan

apply: ## Apply terraform changes — BLOCKED until the state migration completes
	@echo "REFUSED. See docs/state-migration-runbook.md."
	@echo "apply.yml enforces the same gate via STATE_MIGRATION_COMPLETE."
	@exit 1

# ── Utilities ────────────────────────────────────────────────────────────────
list-repos: ## List all managed repositories
	@ls -1 repos/*.yml | sed 's|repos/||;s|\.yml||' | sort

count-repos: ## Count managed repositories
	@echo "Managed repositories: $$(ls -1 repos/*.yml | wc -l)"

clean: ## Remove generated files
	rm -f tfplan plan-output.txt plan.txt compliance-report.json \
	      compliance-snapshot.json quarterly-report.json
