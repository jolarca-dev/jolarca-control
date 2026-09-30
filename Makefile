# ──────────────────────────────────────────────────────────────────────────────
# Jolarca Control Plane — Makefile
# ──────────────────────────────────────────────────────────────────────────────

.PHONY: help setup validate compliance drift fleet-audit org-audit readiness \
        first-commit evidence-check evidence-register \
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

test: ## Regression tests: plan-safety (D-22) + readiness gate + first-commit gate
	bash tests/test_check_plan_safety.sh
	.venv/bin/python -m pytest tests/ -q

# ── Live checks (read-only, need gh / GITHUB_TOKEN) ──────────────────────────
drift: ## Diff the allow-list against the live jolarca-dev org
	python3 scripts/drift_detect.py

fleet-audit: ## ADR-0004 fleet separation guard (R1/R2/R3)
	bash scripts/check_fleet_separation.sh

org-audit: ## Capture the org-wide delivery chain into an evidence bundle
	bash scripts/org_delivery_audit.sh

# Evidence hashing (SOC 2 CC4.1 / ISO 27001 A.5.31 / PCI-DSS 12.10.1).
# The registry is the BASELINE OF RECORD and must be committed: verifying
# against a registry regenerated from the same tree is a tautology that passes
# for every input, which is what evidence-integrity.yml used to do.
#   make evidence-check      # 0 match · 1 changed · 2 no usable baseline
#   make evidence-register   # rewrite the CSV, then commit the diff in a PR
evidence-check: ## Verify evidence hashes against the committed registry
	bash scripts/hash_evidence.sh --check

evidence-register: ## Regenerate docs/evidence-registry.csv (commit the diff)
	bash scripts/hash_evidence.sh

# Pre-first-commit readiness gate. Registry-driven (repos/*.yml), read-only, and
# the only tool that inspects the LOCAL working copy — the gap that let D-28
# (an index holding .idea/ while every real file was untracked) reach commit.
#   make readiness                      # whole allow-list, JSON + table
#   make readiness REPO=jolarca-payments REPORT=/tmp/payments.md OUT=/tmp/payments.json
# Exit 0 all READY · 1 findings · 2 could not verify (never a silent pass).
readiness: ## Per-repo verdict: READY / READY-WITH-FIXES / BLOCKED
	python3 scripts/repo_readiness_audit.py \
	  $(if $(REPO),--repo $(REPO)) \
	  $(if $(OUT),--output $(OUT)) \
	  $(if $(REPORT),--markdown $(REPORT)) >/dev/null

# Phase 3 first-commit pipeline gate — docs/runbooks/first-commit-pipeline.md.
# STRICTLY READ-ONLY: every subprocess call passes an allowlist, so this target
# can verify and instruct but cannot commit, push or merge. The operator runs the
# printed commands. Step A CONSUMES `make readiness` instead of re-implementing
# it, so the two gates cannot drift apart.
#   make first-commit REPO=jolarca-payments STEP=A SNAPSHOT=1
#   make first-commit REPO=jolarca-payments STEP=B MESSAGE="feat: add token vault"
#   make first-commit REPO=jolarca-payments STEP=all EVIDENCE=/tmp/pay-evidence.md
#   make first-commit REPO=jolarca-payments STEP=F ATTEST="G. Kazlauskas" STRICT=1
# Exit 0 every step PASS · 1 findings or tracked exceptions · 2 could not verify.
first-commit: ## Phase 3 gate: VERIFY→COMMIT→PUSH→REVIEW→MERGE→VERIFY (read-only)
	@test -n "$(REPO)" || { \
	  echo "usage: make first-commit REPO=<name> [STEP=A|B|C|D|E|F|all]"; \
	  echo "       [MESSAGE=\"...\"] [ATTEST=\"...\"] [EVIDENCE=<path>] [STRICT=1]"; \
	  echo "       [SNAPSHOT=1] [NO_LIVE=1]"; exit 2; }
	python3 scripts/first_commit_pipeline.py \
	  --repo $(REPO) \
	  $(if $(STEP),--step $(STEP)) \
	  $(if $(MESSAGE),--message "$(MESSAGE)") \
	  $(if $(ATTEST),--attest "$(ATTEST)") \
	  $(if $(EVIDENCE),--evidence $(EVIDENCE)) \
	  $(if $(EXPECTED_SHA),--expected-sha $(EXPECTED_SHA)) \
	  $(if $(SNAPSHOT),--snapshot) \
	  $(if $(STRICT),--strict) \
	  $(if $(NO_LIVE),--no-live) >/dev/null

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
	      compliance-snapshot.json quarterly-report.json \
	      docs/evidence-registry.csv.new
