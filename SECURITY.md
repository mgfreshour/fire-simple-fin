# Security Policy

## Supported versions

This project is small and actively maintained on the default branch. Please report issues against the latest `main`.

## Reporting a vulnerability

Please **do not** open a public GitHub issue for security vulnerabilities.

Prefer [GitHub private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-disclosing-security-vulnerabilities/privately-reporting-a-security-vulnerability) for this repository (Security → Report a vulnerability), if enabled. That keeps the report private until a fix is ready.

If private reporting is unavailable, open a draft [GitHub Security Advisory](https://docs.github.com/en/code-security/security-advisories/working-with-repository-security-advisories/creating-a-repository-security-advisory) or contact the maintainer via GitHub (@mgfreshour) without including secrets in public channels.

Include:

- A short description of the issue and impact
- Steps to reproduce (or a proof of concept)
- Affected version / commit if known

You should receive an acknowledgment when the report is seen. Please allow reasonable time for a fix before any public disclosure.

## Security notes for operators

- This app does **not** store bank login credentials. Bank access uses a SimpleFIN Access URL obtained by claiming a Setup Token.
- Protect the UI and API with a reverse proxy (OAuth2 Proxy, SSO, VPN, or network allowlist). The app itself has no user authentication.
- Do not commit `.env`, `.env.enc`, age private keys, or Firefly tokens. Use `env.example` as a template.
- Set a strong `ENCRYPTION_KEY` before storing connections; Access URLs are encrypted at rest in SQLite.
- Rotate Firefly personal access tokens and re-claim SimpleFIN connections if you suspect compromise.
