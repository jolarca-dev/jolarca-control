# raw probe — sweep6.txt (wrapped 2026-10-26 so hash_evidence.sh:115 covers it)
```
=== T1. Do .github's three workflows even declare workflow_call? ===
--- ci-base.yml ---
  on:
    workflow_call:
      inputs:
        python-version:
          description: 'Python version to use'
          required: false
          default: '3.12'
          type: string
        node-version:
          description: 'Node.js version to use'
          required: false
          default: '20'
--- compliance-base.yml ---
  on:
    workflow_call:
      inputs:
        check-evidence-integrity:
          description: 'Verify evidence file hashes'
          required: false
          default: true
          type: boolean
        check-policy-dates:
          description: 'Check policy review dates'
          required: false
          default: true
--- security-scan.yml ---
  on:
    workflow_call:
      inputs:
        scan-dependencies:
          description: 'Scan dependencies for vulnerabilities'
          required: false
          default: true
          type: boolean
        scan-containers:
          description: 'Scan container images (if present)'
          required: false
          default: false

=== T2. Fleet-wide search for cross-repo reusable-workflow calls ===
CALL  .github/.github/workflows/ci-base.yml  2:# Called by individual repos via: uses: jolarca-dev/.github/.github/workflows/ci-base.yml@main
CALL  .github/.github/workflows/compliance-base.yml  2:# Called by individual repos via: uses: jolarca-dev/.github/.github/workflows/compliance-base.yml@main
CALL  .github/.github/workflows/security-scan.yml  2:# Called by individual repos via: uses: jolarca-dev/.github/.github/workflows/security-scan.yml@main
--- (no CALL lines above = NOTHING in the fleet inherits .github's reusable workflows) ---
```
