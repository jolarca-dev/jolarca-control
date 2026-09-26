# Credential Rotation Runbook — jolarca-dr

## Purpose

This runbook describes how to **rotate all credentials** after a security
incident, infrastructure compromise, or as a preventive measure. It satisfies
PCI-DSS Req 8.3 (credential management) and ISO 27001 A.8.24 (use of cryptography).

## When to Use This Runbook

- Infrastructure compromise suspected or confirmed
- GitHub organization compromise
- Terraform state compromise
- Credential exposure (secret leaked to git history, logs, etc.)
- Post-infrastructure-rebuild (see `runbooks/infrastructure-restore.md`)
- Scheduled rotation (quarterly or per policy)

## Prerequisites

- Access to `jolarca-control` repository
- Access to `jolarca-infrastructure` repository
- `terraform` CLI installed
- `gcloud` CLI installed and authenticated
- `gh` CLI installed and authenticated
- Vault access (if Vault is deployed)
- List of all credentials to rotate (see Checklist below)

## Critical Warning

**Credential rotation is a HIGH-RISK operation.** If done incorrectly, you can:

- Lock yourself out of infrastructure
- Break application functionality
- Cause data loss (if database credentials are rotated incorrectly)
- Trigger false-positive security alerts

**Before proceeding:**
1. Ensure you have a backup of current credentials (Vault snapshot, etc.)
2. Schedule a maintenance window (rotation may cause brief service disruption)
3. Notify stakeholders of potential downtime
4. Have a rollback plan ready

## Procedure

### Phase 1: Inventory Credentials

#### Step 1: List All Credentials

```bash
# GitHub tokens
gh auth status
echo $GITHUB_TOKEN

# GCP service account keys
gcloud iam service-accounts keys list --project=jolarca-marketplace

# Database credentials
gcloud sql users list --instance=marketplace-db --project=jolarca-marketplace

# Vault secrets (if deployed)
vault list secret/data/marketplace

# GitHub Actions secrets
gh api repos/jolarca-dev/jolarca-control/actions/secrets
gh api repos/jolarca-dev/jolarca-infrastructure/actions/secrets
```

**Document:**
- What credentials exist
- Where they are stored
- What services depend on them
- Who/what uses them

#### Step 2: Prioritize Rotation Order

Rotate credentials in this order (least disruptive to most disruptive):

1. **GitHub tokens** (low risk — can be regenerated without service disruption)
2. **GCP service account keys** (medium risk — applications may need restart)
3. **Database credentials** (high risk — applications must be updated immediately)
4. **Vault unseal keys** (critical risk — requires quorum of key holders)

### Phase 2: Rotate GitHub Tokens

#### Step 3: Rotate Personal Access Tokens (PATs)

```bash
# List current tokens
gh api user

# Revoke old tokens
# (Manual: GitHub Settings → Developer settings → Personal access tokens → Delete)

# Generate new tokens
# (Manual: GitHub Settings → Developer settings → Personal access tokens → Generate new token)

# Update local environment
export GITHUB_TOKEN=ghp_new_token_here

# Update Terraform variables
echo 'github_token = "ghp_new_token_here"' > terraform.tfvars
```

**Verify:**
```bash
# Test new token
gh auth status
terraform plan
```

#### Step 4: Rotate GitHub Actions Secrets

```bash
# List current secrets
gh api repos/jolarca-dev/jolarca-control/actions/secrets

# Update secrets
gh secret set GITHUB_TOKEN --body "ghp_new_token_here" --repo jolarca-dev/jolarca-control
gh secret set GCP_SA_KEY --body "$(cat service-account-key.json)" --repo jolarca-dev/jolarca-control

# Repeat for jolarca-infrastructure
gh secret set GITHUB_TOKEN --body "ghp_new_token_here" --repo jolarca-dev/jolarca-infrastructure
gh secret set GCP_SA_KEY --body "$(cat service-account-key.json)" --repo jolarca-dev/jolarca-infrastructure
```

**Verify:**
- Trigger a test workflow to confirm secrets are accessible
- Check workflow logs for authentication errors

### Phase 3: Rotate GCP Service Account Keys

#### Step 5: Rotate Service Account Keys

```bash
# List service accounts
gcloud iam service-accounts list --project=jolarca-marketplace

# List keys for a service account
gcloud iam service-accounts keys list \
  --iam-account=marketplace-sa@jolarca-marketplace.iam.gserviceaccount.com \
  --project=jolarca-marketplace

# Create a new key
gcloud iam service-accounts keys create /tmp/new-key.json \
  --iam-account=marketplace-sa@jolarca-marketplace.iam.gserviceaccount.com \
  --project=jolarca-marketplace

# Update GitHub Actions secrets with new key
gh secret set GCP_SA_KEY --body "$(cat /tmp/new-key.json)" --repo jolarca-dev/jolarca-control
gh secret set GCP_SA_KEY --body "$(cat /tmp/new-key.json)" --repo jolarca-dev/jolarca-infrastructure

# Delete old keys
gcloud iam service-accounts keys delete <old-key-id> \
  --iam-account=marketplace-sa@jolarca-marketplace.iam.gserviceaccount.com \
  --project=jolarca-marketplace \
  --quiet
```

**Verify:**
```bash
# Test new key
export GOOGLE_APPLICATION_CREDENTIALS=/tmp/new-key.json
gcloud auth activate-service-account --key-file=$GOOGLE_APPLICATION_CREDENTIALS
gcloud compute instances list --project=jolarca-marketplace
```

#### Step 6: Rotate Workload Identity Federation (If Configured)

If using Workload Identity Federation (see
`docs/runbooks/workload-identity-federation.md`), no key rotation is needed —
credentials are short-lived and automatically rotated.

**Verify:**
```bash
# Test Workload Identity Federation
gcloud auth login --update-adc
gcloud compute instances list --project=jolarca-marketplace
```

### Phase 4: Rotate Database Credentials

#### Step 7: Rotate Database Passwords

```bash
# Generate a new password
NEW_PASSWORD=$(openssl rand -base64 24)

# Update the database user password
psql -h <db-host> -U marketplace -d marketplace -c "
  ALTER USER marketplace WITH PASSWORD '$NEW_PASSWORD';
"

# Update application configuration
# (depends on deployment method — environment variable, config file, etc.)
export DATABASE_PASSWORD=$NEW_PASSWORD

# Restart application services
systemctl restart marketplace-api
```

**Verify:**
```bash
# Test new credentials
psql -h <db-host> -U marketplace -d marketplace -c "SELECT 1;"

# Test application connectivity
curl -I https://marketplace.jolarca.dev/health
```

#### Step 8: Rotate Database Service Account (GCP)

If the application uses a GCP service account to connect to Cloud SQL:

```bash
# The service account key was already rotated in Phase 3
# Verify the application can connect using the new key
psql -h <db-host> -U marketplace -d marketplace -c "SELECT 1;"
```

### Phase 5: Rotate Vault Secrets (If Deployed)

#### Step 9: Rotate Vault Secrets

```bash
# List secrets
vault list secret/data/marketplace

# Update a secret
vault kv put secret/marketplace/database \
  username=marketplace \
  password=$NEW_PASSWORD

# Verify
vault kv get secret/marketplace/database
```

#### Step 10: Rotate Vault Unseal Keys (Critical)

**WARNING:** This requires a quorum of key holders and will temporarily make
Vault unavailable.

```bash
# This procedure depends on your Vault configuration
# See Vault documentation for unseal key rotation

# General steps:
# 1. Generate new unseal keys
# 2. Distribute new keys to key holders
# 3. Re-seal Vault
# 4. Unseal Vault with new keys
# 5. Verify Vault is operational
```

**Verify:**
```bash
vault status
vault kv get secret/marketplace/database
```

### Phase 6: Post-Rotation Tasks

#### Step 11: Update Documentation

Update all documentation that references rotated credentials:

- `docs/runbooks/workload-identity-federation.md` (if applicable)
- Application deployment guides
- Onboarding documentation

**Do NOT commit actual credentials to documentation.**

#### Step 12: Verify All Services

```bash
# Test all critical services
curl -I https://marketplace.jolarca.dev/health
curl -I https://api.marketplace.jolarca.dev/users

# Run smoke tests
pytest tests/

# Check application logs for authentication errors
gcloud logging read "severity>=ERROR" --limit=100
```

#### Step 13: Document the Rotation

Record the rotation in `jolarca-compliance`:

- **Timestamp:** When the rotation was performed
- **Credentials rotated:** List of all credentials rotated
- **Reason:** Why the rotation was performed (incident, scheduled, etc.)
- **Operator:** Who performed the rotation
- **Verification:** How the rotation was verified
- **Incident reference:** Link to incident record (if applicable)

#### Step 14: Clean Up

```bash
# Delete temporary key files
rm /tmp/new-key.json
rm /tmp/db-restore.sql

# Verify no credentials remain in shell history
history | grep -i password
history | grep -i token

# Clear shell history if needed
history -c
```

## Credential Rotation Checklist

### GitHub

- [ ] Personal access tokens rotated
- [ ] GitHub Actions secrets updated
- [ ] Webhook secrets rotated (if applicable)
- [ ] SSH keys rotated (if applicable)

### GCP

- [ ] Service account keys rotated
- [ ] Workload Identity Federation verified (if configured)
- [ ] API keys rotated (if applicable)
- [ ] GCS HMAC keys rotated (if applicable)

### Database

- [ ] Database passwords rotated
- [ ] Application configuration updated
- [ ] Connection pools restarted
- [ ] Backup credentials rotated (if separate)

### Vault (If Deployed)

- [ ] Vault secrets rotated
- [ ] Vault unseal keys rotated (if required)
- [ ] Vault tokens rotated
- [ ] Vault policies verified

### Applications

- [ ] Environment variables updated
- [ ] Configuration files updated
- [ ] Services restarted
- [ ] Smoke tests passed

### Documentation

- [ ] Runbooks updated
- [ ] Deployment guides updated
- [ ] Onboarding documentation updated
- [ ] Rotation recorded in `jolarca-compliance`

## Troubleshooting

### "Application cannot authenticate after credential rotation"

**Cause:** Application is using old credentials.

**Resolution:**
1. Verify application configuration has been updated
2. Restart application services
3. Check application logs for authentication errors
4. Verify new credentials are correct

### "terraform plan fails with authentication error"

**Cause:** GitHub token or GCP service account key is invalid.

**Resolution:**
```bash
# Verify GitHub token
gh auth status

# Verify GCP credentials
gcloud auth list

# Update credentials if needed
export GITHUB_TOKEN=ghp_new_token_here
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/new-key.json
```

### "Database connection fails after password rotation"

**Cause:** Application is using old database password.

**Resolution:**
1. Verify `DATABASE_PASSWORD` environment variable is set correctly
2. Restart application services
3. Check application logs for connection errors
4. Verify database user exists and password is correct

## Compliance Mapping

| Framework | Control | Requirement |
|---|---|---|
| PCI-DSS | Req 8.3 | Credential management — rotation policy |
| ISO 27001 | A.8.24 | Use of cryptography — key management |
| SOC 2 | CC6.1 | Logical access — credential rotation |
| GDPR | Art. 32 | Security of processing — credential management |

## References

- `policies/backup-policy.md` — Backup frequency and retention
- `runbooks/infrastructure-restore.md` — Infrastructure rebuild procedure
- `docs/runbooks/workload-identity-federation.md` — Workload Identity Federation
- `docs/runbooks/github-token-rotation.md` — GitHub token rotation (jolarca-control)
