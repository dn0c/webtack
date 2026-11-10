# Security Policy

The WebTack project treats security, data integrity, and curator privacy as foundational requirements. Because WebTack manages personal knowledge archives that may include private notes, sensitive reading habits, and private media, we maintain strict privacy boundaries across all egress and storage pipelines.

---

## Supported Versions

Security patches and vulnerability assessments are provided for the following versions:

| Version | Supported | Notes |
| :--- | :--- | :--- |
| **v3.x / `main`** | ✅ Supported | Canonical Content Architecture |
| **< v3.0** | ❌ Unsupported | Legacy prototypes (deprecated) |

---

## Reporting a Vulnerability

If you discover a security vulnerability or sensitive information disclosure in WebTack:

1. **Do not disclose the issue publicly** in a public GitHub issue, pull request, or forum.
2. **Submit via GitHub Private Vulnerability Reporting**:
   - Navigate to the **Security** tab of the [WebTack GitHub repository](https://github.com/dn0c/webtack).
   - Click **Report a vulnerability** under "Private vulnerability reporting".
3. **Alternative direct contact**:
   - If GitHub Private Reporting is unavailable, email **`andrew.w.shannon@gmail.com`** with the subject line `[SECURITY] WebTack Vulnerability Report`.
   - Include a description of the issue, steps to reproduce or proof-of-concept, and the potential impact.

### Response Timeline
- **Initial Response**: Within 48 hours acknowledging receipt of the report.
- **Triage & Assessment**: Within 5 business days with an assessment of severity and a remediation plan.
- **Coordinated Disclosure**: Once a patch is merged and verified, an advisory will be published and credit will be given to the reporter.

---

## Security & Privacy Architecture

WebTack follows several defense-in-depth principles:

### 1. Local-First Boundary
* The web viewer (`viewer.py`) binds strictly to `127.0.0.1:8080` by default. It does not bind to `0.0.0.0` unless explicitly instructed via CLI flags.
* No telemetry, phone-home metrics, or analytics scripts are embedded in the software.

### 2. Egress & Privacy Tiering
Every atom enforces an explicit `curation.visibility` classification:
* **`private`**: Strictly restricted to local disk. Excluded from all public SQLite queries, cloud synchronizers (`curate.py sync`), and web garden manifests.
* **`shared`**: Restricted to collaborative circles and explicitly filtered exports. Excluded from public cloud sync.
* **`public`**: Digital garden syndicate.

### 3. Secret Management
* All generative AI tokens (`GEMINI_API_KEY`, `OPENAI_API_KEY`, etc.), cloud bucket names, and session credentials must reside in local `.env` files.
* `.env`, `.env.*`, `*cookie*.txt`, and `.sync_credentials.json` are strictly excluded from git tracking via [`.gitignore`](.gitignore).
