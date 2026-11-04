# raw probe — verify3.txt (wrapped 2026-10-26 so hash_evidence.sh:115 covers it)
```
=== BASELINE (my files removed) ===
readiness_exit_baseline=1

=== restored ===
?? docs/master-architect-prompt.md
?? docs/pre-deployment-audit-2026-10-24.md

=== how does CI invoke readiness? ===
.github/workflows/compliance-scan.yml-129-
.github/workflows/compliance-scan.yml-130-  # ── Context 3: Repository Secret Pattern Scan ──────────────────────────────
.github/workflows/compliance-scan.yml:131:  # The full readiness audit (scripts/repo_readiness_audit.py) checks local
.github/workflows/compliance-scan.yml-132-  # state that differs between CI and a developer machine (git config,
.github/workflows/compliance-scan.yml-133-  # branch state, CODEOWNERS resolution). Running it as a required context
.github/workflows/compliance-scan.yml-134-  # deadlocked the merge gate. The secret scan itself is simpler: gitleaks
.github/workflows/compliance-scan.yml-135-  # covers tracked files AND history with the project's .gitleaks.toml.
.github/workflows/compliance-scan.yml-136-  secret-scan:
.github/workflows/compliance-scan.yml-137-    name: Repository Secret Pattern Scan
--
.github/workflows/context-parity.yml-8-# `gitleaks (full history)`. Under strict:true that is an unsatisfiable gate -- every
.github/workflows/context-parity.yml-9-# future PR there would block forever once applied. The computation already existed in
.github/workflows/context-parity.yml:10:# scripts/repo_readiness_audit.py but no workflow invoked it, so the defect was only
.github/workflows/context-parity.yml-11-# ever found by hand. A detection no pipeline runs is folklore, not a control (D-22).
.github/workflows/context-parity.yml-12-#
.github/workflows/context-parity.yml-13-# Scope is deliberately narrow: the full readiness audit currently reports 15 of 16
.github/workflows/context-parity.yml-14-# repos BLOCKED for unrelated reasons, so gating CI on it would be red every week and
.github/workflows/context-parity.yml-15-# train dismissal. Exit codes are the fleet's three-valued contract -- 0 clean,
.github/workflows/context-parity.yml-16-# 1 findings, 2 could-not-verify -- and 2 never reads as a pass (D-23).
--
.github/workflows/sast.yml-116-      # real finding. Any accepted false positive MUST carry an inline
.github/workflows/sast.yml-117-      # `# nosec Bxxx` with a rationale comment (see the B108 suppression
.github/workflows/sast.yml:118:      # at tests/test_repo_readiness_audit.py:489 as the pattern).
.github/workflows/sast.yml-119-      - name: Run bandit
.github/workflows/sast.yml-120-        run: bandit -r scripts/ tests/ -ll -ii
.github/workflows/sast.yml-121-
.github/workflows/sast.yml-122-  # ── Trivy config scan (Terraform source + workflow YAML + policy YAML) ─────
.github/workflows/sast.yml-123-  # Covers the "as feasible" clause in the A-08 prompt: Terraform at repo
.github/workflows/sast.yml-124-  # root, `.github/workflows/` YAML (actions permissions, checkout pin
```
