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
- **Fix or mitigation** as soon as feasible, depending on severity
- **Credit** in the release notes (unless you prefer anonymity)

### Scope

The following are in scope:

- The Sims 4 Updater application (`Sims4Updater.exe`)
- The Python source code in this repository
- CDN and API endpoints (`cdn.hyperabyss.com`, `api.hyperabyss.com`)

The following are out of scope:

- Third-party dependencies (report to the respective maintainers)
- Social engineering attacks
- Denial of service attacks

## Security Features

This repository has the following security measures enabled:

- **Dependabot alerts** — automatic notifications for vulnerable dependencies
- **Dependabot security updates** — automatic PRs to fix vulnerable dependencies
- **Secret scanning** — prevents accidental secret commits
- **CodeQL analysis** — automated static analysis for common vulnerabilities
- **Private vulnerability reporting** — confidential disclosure channel
