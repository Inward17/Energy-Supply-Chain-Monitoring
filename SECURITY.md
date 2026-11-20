# Security Policy

## Supported versions

Only the `main` branch, which is what is deployed to
<https://energy-supply-chain.pages.dev> and its API, receives security fixes.

## Reporting a vulnerability

**Please do not open a public issue for a vulnerability.**

Report it privately through GitHub: **Security → Report a vulnerability** on
this repository (private vulnerability reporting). Only the maintainer can see
the report.

If that option is not available, open an issue that says only that you have a
security report and need a private channel — no details — and the maintainer
will reach out.

Please include:

- what is affected (endpoint, page, file) and the impact you expect,
- steps to reproduce or a proof of concept,
- any suggested fix.

You can expect an acknowledgement within 7 days. Fixes are made on a branch
and released through a normal pull request once ready; you will be credited in
the advisory unless you prefer otherwise.

## Scope

In scope: the FastAPI backend (`backend/`), the MERIDIAN frontend
(`frontend/`), the GitHub Actions workflows and the Docker setup.

Out of scope: `legacy/frontend/` (not deployed), third-party services
(Render, Cloudflare, Neon, Neo4j Aura, Gemini, data providers), and findings
that need a compromised maintainer account or machine.

## What is already in place

- The dashboard is public and read-only. Starting a backtest (hundreds of
  Gemini calls) requires the maintainer's `ADMIN_API_KEY`. War Room AI briefs
  are capped per day in Postgres, on top of bounded inputs and per-client +
  global rate limits.
- Secrets live only in platform settings and GitHub secrets; `.env` files are
  git-ignored and excluded from images.
- CodeQL, Dependabot and GitGuardian run on every pull request.
- The frontend is served with a CSP, HSTS and `X-Frame-Options: DENY`.

Known limitations are tracked in [`TECHNICAL_DEBT.md`](TECHNICAL_DEBT.md).
