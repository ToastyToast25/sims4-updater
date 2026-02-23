# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 2.x.x   | Yes               |
| < 2.0   | No                |

## Reporting a Vulnerability

We take security seriously. If you discover a vulnerability, please report it responsibly.

### Preferred: GitHub Private Vulnerability Reporting

1. Go to the [Security Advisories](https://github.com/ToastyToast25/sims4-updater/security/advisories) page
2. Click **"Report a vulnerability"**
3. Fill in the details and submit

This is the fastest way to reach us and keeps the report confidential until a fix is ready.

### Alternative: Email

If you cannot use GitHub's reporting, email **toastytoast25@proton.me** with:

- Description of the vulnerability
- Steps to reproduce
- Impact assessment
- Any suggested fixes

### What to Expect

- **Acknowledgment** within 48 hours
- **Initial assessment** within 1 week
- **Credit** in the release notes (unless you prefer anonymity)

### Response SLAs by Severity

| Severity | Example | Target Fix |
| -------- | ------- | ---------- |
| Critical | Remote code execution, auth bypass | 7 days |
| High | Privilege escalation, credential leak | 14 days |
| Medium | Information disclosure, path traversal | 30 days |
| Low | Minor info leak, debug output | Next release |

### Scope

The following are in scope:

- The Sims 4 Updater application (`Sims4Updater.exe`)
- The Python source code in this repository
- CDN and API endpoints (`cdn.example.com`, `api.example.com`)

The following are out of scope:

- Third-party dependencies (report to the respective maintainers)
- Social engineering attacks
- Denial of service attacks

## Security Features

This repository has the following security measures enabled:

- **Dependabot alerts** — automatic notifications for vulnerable dependencies
- **Dependabot security updates** — automatic PRs to fix vulnerable dependencies
- **Secret scanning** — prevents accidental secret commits with push protection
- **CodeQL analysis** — automated static analysis for common vulnerabilities
- **Dependency review** — blocks PRs that introduce high-severity vulnerable dependencies
- **pip-audit** — scans installed packages for known CVEs on every CI run
- **Artifact attestations** — cryptographic provenance for release binaries
- **SHA256 checksums** — `SHA256SUMS.txt` published with every release
- **Private vulnerability reporting** — confidential disclosure channel
- **Branch protection** — required status checks, admin enforcement, conversation resolution

## Verifying Downloads

Every release includes a `SHA256SUMS.txt` file. To verify your download:

```bash
# Linux/macOS
sha256sum -c SHA256SUMS.txt

# Windows (PowerShell)
Get-FileHash Sims4Updater.exe -Algorithm SHA256
# Compare output with the hash in SHA256SUMS.txt
```

Artifact attestations can be verified with the GitHub CLI:

```bash
gh attestation verify Sims4Updater.exe --repo ToastyToast25/sims4-updater
```
