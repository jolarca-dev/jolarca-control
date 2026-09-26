# Payment Security Policy — jolarca-payments

## Metadata

| Attribute | Value |
|---|---|
| Policy Owner | jolarca-dev organization owner |
| Classification | Internal |
| Compliance | PCI-DSS 4.0 Req. 12.1, SOC 2 CC9.2, ISO 27001 A.5.1 |
| Last Reviewed | 2026-09-26 |
| Next Review | 2026-12-26 |
| Approved By | Gintaras Kazlauskas |

---

## 1. Purpose

This policy establishes the security requirements for payment processing within
the `jolarca-dev` marketplace. It defines the controls that protect cardholder
data throughout its lifecycle — from acquisition through transmission,
processing, storage, and deletion.

## 2. Scope

This policy applies to:

- All systems, processes, and personnel that store, process, or transmit
  cardholder data (the cardholder-data environment, or CDE)
- All code, configuration, and policy in this repository
- All payment provider integrations and their configurations
- All personnel with access to payment systems or cardholder data

## 3. Policy Statements

### 3.1 Cardholder Data Protection

- Cardholder data MUST be encrypted at rest using AES-256 or equivalent
- Cardholder data MUST be encrypted in transit using TLS 1.2 or higher
- Primary Account Numbers (PAN) MUST be rendered unreadable anywhere they are
  stored (PCI-DSS Req. 3.4)
- Full track data, CVV2/CVC2, and PINs/PIN blocks MUST NOT be stored after
  authorization (PCI-DSS Req. 3.2)

### 3.2 Access Control

- Access to CDE systems MUST follow the principle of least privilege (PCI-DSS Req. 7)
- Access MUST be granted on a need-to-know basis and documented
- All access to cardholder data MUST be logged and monitored (PCI-DSS Req. 10)
- Service accounts accessing the CDE MUST use unique credentials

### 3.3 Network Segmentation

- The CDE MUST be logically separated from non-CDE systems (PCI-DSS Req. 1)
- Network access controls MUST restrict traffic between the CDE and other networks
- Segmentation controls MUST be reviewed and tested at least annually

### 3.4 Cryptographic Key Management

- Cryptographic keys MUST be managed in accordance with the key management
  procedure (see `pci-dss/key-management.md`)
- Keys MUST be rotated at least annually or when compromise is suspected
- Key material MUST NEVER be committed to source control

### 3.5 Change Control

- All changes to CDE systems MUST follow the change control process (PCI-DSS Req. 6.3)
- Changes MUST be tested in a non-production environment before deployment
- Changes MUST be documented with business justification and impact assessment

### 3.6 Incident Response

- Payment security incidents MUST be responded to in accordance with the
  incident response runbook (see `runbooks/incident-response.md`)
- Card brand notification requirements MUST be met within the timeframes
  specified by each brand's compliance program

## 4. Compliance

Violations of this policy may result in:

- Loss of payment processing capability
- Fines and penalties from card brands
- Regulatory action under GDPR or other applicable law
- Reputational damage and loss of customer trust

## 5. Related Documents

- [Data Classification Policy](data-classification.md)
- [Encryption Policy](encryption-policy.md)
- [PCI-DSS Scope Definition](../pci-dss/scope-definition.md)
- [Key Management Procedures](../pci-dss/key-management.md)
- [Incident Response Runbook](../runbooks/incident-response.md)
