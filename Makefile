# ──────────────────────────────────────────────────────────────────────────────
# Jolarca Control Plane — Makefile
# ──────────────────────────────────────────────────────────────────────────────

.PHONY: help setup validate compliance context-parity context-baseline backup adoption-block drift fleet-audit org-audit readiness \
        first-commit evidence-check evidence-register findings-check gate-parity secrets-inventory \
        apply-path-trigger \
        init fmt fmt-check lint tf-validate py-lint py-fmt-check py-type sh-lint yaml-lint \
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

lint: fmt-check tf-validate validate context-baseline gate-parity py-lint py-fmt-check py-type sh-lint yaml-lint test ## Everything CI runs before a plan

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

# D-83: `fmt-check` above is TERRAFORM fmt; `lint` ran no ruff formatter check, while the CI Lint
# job does run `ruff format --check`. Measured 2026-10-26: `lint` exited 0 (313 passed) on a branch
# whose new fixture file that check wanted to reformat in 13 places. This is NOT an unenforced
# formatter — `.pre-commit-config.yaml` carries `ruff-format`, the hook is installed, and
# `pre-commit run --all-files` passes all twelve — so the gap is that the surface AGENTS.md §2 tells
# people to run (`make lint`) does not match CI's list, and a session can sit inside `lint` without
# ever invoking the hooks. `lint` now covers it; the three surfaces (lint / hooks / CI) are still
# compared by nothing.
py-fmt-check: ## ruff format --check over scripts/ and tests/ (the check the CI Lint job runs)
	ruff format --check scripts/ tests/

py-type: ## mypy --strict over scripts/ (config in pyproject.toml)
	mypy

sh-lint: ## shellcheck over every shell script
	shellcheck -x scripts/*.sh tests/*.sh

yaml-lint: ## yamllint over the repo (config: .yamllint; not --strict, see file)
	yamllint -c .yamllint .

test: ## Regression tests: plan-safety (D-22) + execution mode + evidence integrity + credential expiry + backup (D-02)
	bash tests/test_check_plan_safety.sh
	bash tests/test_check_workspace_execution_mode.sh
	bash tests/test_hash_evidence.sh
	bash tests/test_check_secret_inventory.sh
	bash tests/test_state_backup.sh
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

# Gate parity: the control that gates the controls (D-80).
# AGENTS.md §7 requires a negative control for every gate and §3 requires 0/1/2 exits, but
# nothing checked either rule, so both rotted unnoticed: scripts/check_secret_inventory.sh
# landed unwired and untested, and tests/test_check_workspace_execution_mode.sh (13 cases)
# ran only via this Makefile — never in CI, where `pytest tests/` collects .py and cannot
# collect .sh. Offline, deterministic, no credentials.
#   0 parity · 1 findings · 2 could not verify (unreadable Makefile or workflow)
gate-parity: ## Every gate must have a fixture, and every fixture must actually run
	python3 scripts/check_gate_parity.py

# Credential expiry, read from the machine-read table in docs/security/key-custody.md.
# STATUS 2026-10-26: exits 1 by design — the TFC_TOKEN row's expiry is `unknown` until the
# operator reads it in the HCP UI, which is what that register itself says. Deliberately NOT a
# `lint` prerequisite: a permanently-red local gate trains everyone to ignore red. It runs in
# deploy-gates.yml, an advisory job, so the signal is visible without blocking every merge.
# Promote it to a required context only once the row carries a real date.
secrets-inventory: ## Fail if a dated credential is expired, imminent, or has an unknown expiry
	bash scripts/check_secret_inventory.sh

# Would this branch's diff arm a production apply, and who authored it? (D-81)
# apply.yml triggers on `push: main` for repos/**, policy/**, *.tf, *.tfvars and itself, then
# applies with -auto-approve; a pinned-action bump inside apply.yml therefore is a deploy change,
# not a dependency chore. Run it on a feature branch: on main the diff against origin/main is
# empty, and the script reports 2 (could not verify) rather than calling an unread diff clean.
# Deliberately NOT a `lint` prerequisite: it needs a branch-relative diff that a detached CI
# checkout may not have, and a red from checkout shape would be an artefact, not a finding.
#   0 no trigger match, or a human changed one (announced) · 1 a bot would arm it · 2 unverifiable
apply-path-trigger: ## Report whether this branch would start a production apply, and by whom
	python3 scripts/check_apply_path_trigger.py --changed "$$(git diff --name-only origin/main...HEAD)"

# Pre-first-commit readiness gate. Registry-driven (repos/*.yml), read-only, and
# the only tool that inspects the LOCAL working copy — the gap that let D-28
# (an index holding .idea/ while every real file was untracked) reach commit.
#   make readiness                      # whole allow-list, JSON + table
#   make readiness REPO=jolarca-payments REPORT=/tmp/payments.md OUT=/tmp/payments.json
# Exit 0 all READY · 1 findings · 2 could not verify (never a silent pass).
# A-07 register-integrity guard. Detects a `### D-nn` heading duplicated on the working copy, or
# claimed with a different title by main and an open PR branch -- the collision that PR #41 and main
# both hit on D-52 (2026-10-05), and that PR #67 and this branch reproduced on D-58 (2026-10-16).
# Before the guard existed, allocating D-69 required a hand-run grep for the highest id.
# 0/1/2 like every other gate here: an unparseable register is 2, never a pass (D-23).
# The CI step in the required `Validate Repo Allow-List` job runs the same script WITHOUT
# --cross-pr, because a cross-PR failure would block every merge on an unrelated open branch;
# use this target before opening a PR, where that trade-off is worth paying.
findings-check: ## Every `### D-nn` heading must be unique on main and across open PRs
	python3 scripts/check_findings_register.py --cross-pr

readiness: ## Per-repo verdict: READY / READY-WITH-FIXES / BLOCKED
	# No `>/dev/null` here: this script puts its one-line table on stderr and its
	# detail (findings JSON when OUT= is omitted) on stdout, so redirecting stdout
	# silently threw the findings away while leaving the table to imply the gate
	# had simply been terse (D-86, measured 2026-10-26).
	# NOTE: `make readiness` can never report §3's three-valued code — GNU make
	# returns 2 for any failed recipe (proved: a `@exit 1` target also yields 2).
	# Call `.venv/bin/python scripts/repo_readiness_audit.py …` directly when the
	# difference between "findings" (1) and "could not verify" (2) matters.
	python3 scripts/repo_readiness_audit.py \
	  $(if $(REPO),--repo $(REPO)) \
	  $(if $(OUT),--output $(OUT)) \
	  $(if $(REPORT),--markdown $(REPORT))
context-parity: ## Declared required status checks must be checks the repo can report
	python3 scripts/check_declared_contexts.py

context-baseline: ## policy/repo-defaults.yml required_checks must match the declaration AND be producible (D-62)
	python3 scripts/check_required_context_baseline.py

# Off-host encrypted backup of Terraform state, with the decrypt round trip
# PROVEN before it reports success (D-02). BACKUP_DEST is required because a
# backup written next to the thing it backs up is not a 3-2-1 backup.
#   BACKUP_DEST=/opt/jolarca/backups make backup
backup: ## Encrypted, decrypt-verified off-host backup of Terraform state
	@test -n "$(BACKUP_DEST)" || { echo "usage: BACKUP_DEST=<off-host-dir> make backup"; exit 1; }
	BACKUP_DEST=$(BACKUP_DEST) bash scripts/state_backup.sh

# Step 6b step 1 of docs/state-migration-runbook.md. The instruction used to be "land this file only
# in the PR that runs step 2", i.e. transcribe a protection object by hand — the friction D-87 row
# (3) says trains humans to hand-write protection objects. Two scripted replacements for that failed
# in structurally different ways before this target existed: a word filter dropped the adoption block
# because its own comment mentions `pull_request`, and an awk variant emitted zero lines which
# `terraform fmt -check` then reported as clean. So this extracts by BLOCK syntax, asserts the result
# is inert, and refuses rather than write something an operator will import.
#   make adoption-block                 # writes rulesets.tf (refuses if it already exists)
#   make adoption-block OUT=/tmp/preview.tf
#   0 one inert adoption · 1 refused (ambiguous, contaminated, or would overwrite) · 2 cannot verify
adoption-block: ## Extract Step 6b's inert adoption block for terraform import
	python3 scripts/extract_adoption_block.py --out $(if $(OUT),$(OUT),rulesets.tf)

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
	# As in `readiness` above: stdout carries the machine-readable verdict, so it
	# is no longer discarded, and a non-zero exit here is make's generic 2, not
	# this script's 1-or-2 — invoke the script directly to read the real code (D-86).
	python3 scripts/first_commit_pipeline.py \
	  --repo $(REPO) \
	  $(if $(STEP),--step $(STEP)) \
	  $(if $(MESSAGE),--message "$(MESSAGE)") \
	  $(if $(ATTEST),--attest "$(ATTEST)") \
	  $(if $(EVIDENCE),--evidence $(EVIDENCE)) \
	  $(if $(EXPECTED_SHA),--expected-sha $(EXPECTED_SHA)) \
	  $(if $(SNAPSHOT),--snapshot) \
	  $(if $(STRICT),--strict) \
	  $(if $(NO_LIVE),--no-live)

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
	@echo "apply.yml checks STATE_MIGRATION_COMPLETE, which measures 'true' — so that"
	@echo "gate is OPEN and this local refusal is the only one that stops YOU. In CI the"
	@echo "refusal is scripts/check_plan_safety.sh (destroy/replace/visibility/"
	@echo "branch-protection/security-feature disables). See D-61 and D-58."
	@exit 1

# ── Utilities ────────────────────────────────────────────────────────────────
list-repos: ## List all managed repositories
	@ls -1 repos/*.yml | sed 's|repos/||;s|\.yml||' | sort

count-repos: ## Count managed repositories
	@echo "Managed repositories: $$(ls -1 repos/*.yml | wc -l)"

clean: ## Remove generated files
	rm -f tfplan plan-output.txt plan.txt workspace.json compliance-report.json \
	      compliance-snapshot.json quarterly-report.json \
	      docs/evidence-registry.csv.new
