# raw probe — final2.txt (wrapped 2026-10-26 so hash_evidence.sh:115 covers it)
```
=== gitleaks DIR scan (covers untracked files, which 'gitleaks git .' does NOT) ===
[90m6:56PM[0m [32mINF[0m [1mscanned ~715548 bytes (715.55 KB) in 80.5ms[0m
[90m6:56PM[0m [32mINF[0m [1mno leaks found[0m
dir_exit=0

=== direct grep for credential-shaped strings in the two new docs ===
--- (empty above = no full-length credential-shaped literals) ---

=== the age-key mention, as written ===
docs/pre-deployment-audit-2026-10-24.md:473:plaintext secret material. The `.sops.yaml` value is an **age public key** (`age1h6knx…`) — public
```
