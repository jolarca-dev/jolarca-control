# raw probe — verify1.txt (wrapped 2026-10-26 so hash_evidence.sh:115 covers it)
```
=== what does check_findings_register.py scan? ===
6:`docs/drift-findings.md` is the authoritative D-series register. Its finding IDs are
7:referenced from SECURITY.md, `audit/*.yml`, `docs/threat-model.md`, `policy/**`,
23:1) **Intra-file** -- same `D-nn` heading appearing twice in `docs/drift-findings.md`.
44:from pathlib import Path
47:ROOT = Path(__file__).resolve().parent.parent
57:REGISTER_REF_PATH = "docs/drift-findings.md"
144:    headings: list[tuple[str, str]], root: Path = ROOT
196:                    "`### <id> · <title>` heading exists in docs/drift-findings.md; add the row "

=== RUN: findings register ===
OK: 78 `### D-nn` headings parsed, no collisions, no dangling citations
exit=0

=== RUN: evidence-check ===
bash scripts/hash_evidence.sh --check

Evidence check: 39 files scanned, 0 mismatches
OK: all registered evidence hashes match
exit=0

=== RUN: validate ===
python3 scripts/validate_repos.py
PASSED — 16 repo definitions validated successfully.
exit=0
```
