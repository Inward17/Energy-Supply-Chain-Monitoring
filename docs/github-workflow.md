# GitHub workflow: PRs, reviews, bots and CI/CD for MERIDIAN

How changes travel from your laptop to production, what each GitHub feature
does along the way, and how it connects to Cloudflare Pages, Render and Neon.
Section 7 walks through a PR end to end.

---

## 1. The big picture

```
 your laptop                         GitHub                                   production
 ───────────                         ──────                                   ──────────
 git switch -c feat/x
 edit, commit
 git push ───────────────►  branch feat/x
                            gh pr create ──► Pull Request #N
                                              │
                                              ├─ Frontend CI   (GitHub Actions)   typecheck · build · smoke tests
                                              ├─ Backend CI    (GitHub Actions)   pytest on a Neon branch of the DB
                                              ├─ CodeQL        (GitHub Actions)   security scan
                                              ├─ Cloudflare Pages (bot)           preview URL for this PR
                                              ├─ AI reviewer   (bot, optional)    line comments
                                              └─ you           (human review)     read diff, try preview
                                              │
                                    all green + approved
                                              │
                                        Merge to main ─────────────►  Cloudflare Pages  → energy-supply-chain.pages.dev
                                                                    ─►  Render (after CI) → backend API
                                                                          └─ Neon: PR's database branch deleted

 every hour, on main:  ingest.yml ──► cron_worker.py --once --with ais ──► Neon / AuraDB
```

The rule that makes it all work: **`main` is always deployable.** Nothing
lands on `main` except through a PR whose checks passed. Deploys are then
automatic, because anything on `main` has already been verified.

---

## 2. The pieces, in plain terms

| Term | What it is | Where it lives |
|---|---|---|
| **Branch** | A parallel line of commits. Work happens on `feat/…` or `fix/…`, never directly on `main`. | `git switch -c feat/name` |
| **Pull request (PR)** | A proposal to merge a branch into `main`. It's the place for diff, discussion, checks and approval. | GitHub → Pull requests |
| **GitHub Actions** | GitHub's CI runner. A **workflow** (YAML) has **jobs** that run **steps** on a fresh VM. | `.github/workflows/*.yml` |
| **Check / status check** | One pass/fail result shown on a PR. Each job is one check (e.g. `Frontend CI / verify`). Apps like Cloudflare add their own. | PR → Checks tab |
| **Required check** | A check that must be green before the merge button unlocks. | Settings → Rules |
| **Ruleset / branch protection** | Rules on `main`: require PRs, require checks, block force-push, etc. | Settings → Rules → Rulesets |
| **Review** | Comment / Approve / Request changes on a PR. Line comments sit on specific diff lines. | PR → Files changed |
| **CODEOWNERS** | Maps paths to people who get auto-requested for review. | `.github/CODEOWNERS` |
| **PR template** | Pre-fills every new PR description with a checklist. | `.github/pull_request_template.md` |
| **Bot / GitHub App** | An automated account that reacts to PRs: comments, checks, opens PRs. | Settings → Integrations |
| **Dependabot** | GitHub's bot that opens PRs to upgrade dependencies and flags vulnerable ones. | `.github/dependabot.yml` |
| **CodeQL** | GitHub's static security analyser. Free for public repos. | `.github/workflows/codeql.yml` |
| **Secrets** | Encrypted values workflows can read (API keys). Never in code. | Settings → Secrets and variables → Actions |
| **Preview deployment** | A full deploy of a PR's branch at its own URL, so you can click around before merging. | Cloudflare Pages, automatic |
| **CD (continuous deployment)** | Merging to `main` triggers the production deploy. | Cloudflare + Render, automatic |

---

## 3. What is set up in this repo

| File | What it does |
|---|---|
| `.github/workflows/frontend-ci.yml` | On every PR: typecheck → static build (exactly what Cloudflare deploys) → Playwright smoke tests on desktop and phone sizes. It skips itself in seconds when `frontend/` is untouched, so it can be a *required* check without blocking backend-only PRs. On failure it uploads the Playwright report as an artifact. |
| `frontend/tests/smoke.spec.ts` | 5 tests: the shell loads; every page renders without a crash; the sidebar shows on desktop; the 5-tab bar shows on phones with no sideways scroll on any page; the theme toggle persists across reloads. The app is built against a closed port, so tests need no backend, database or secrets. |
| `frontend/playwright.config.ts` | Serves `out/` with Python's built-in HTTP server, and runs a desktop (1440×900) and a phone (Pixel 5) project. |
| `.github/workflows/backend-ci.yml` | On every PR touching `backend/`: Python 3.13 (matches the Dockerfile) → `pip install` → `pytest` (~180 tests). The database is a **Neon branch per PR** when Neon is configured, otherwise a throwaway Postgres container on the runner (see §4). Like frontend CI, it always reports, so it can be required. |
| `.github/workflows/neon-cleanup.yml` | When a PR is merged or closed, deletes its Neon branch `ci/pr-<number>`. |
| `.github/workflows/codeql.yml` | Security scan of TypeScript and Python on PRs, on `main`, and weekly. Ignores `legacy/`. |
| `.github/workflows/ingest.yml` | Hourly data ingestion against production (Neon + AuraDB), independent of the Render instance sleeping. Skips itself until the database secrets exist. See `DEPLOYMENT.md` §4. |
| `.github/dependabot.yml` | Weekly grouped upgrade PRs for `frontend/` (npm) and `backend/` (pip); monthly for GitHub Actions. Ignore rules hold back upgrades known to break: TypeScript 7 and `@types/node` majors, `google-genai` 3 (its default API version 404s our model) and the `websockets` / `tenacity` versions that need it. |
| `.github/pull_request_template.md` | What / how to verify / checklist / deployment notes. |
| `.github/CODEOWNERS` | `@Inward17` owns everything (auto-requested as reviewer). |
| `backend/api.py` → `CORS_ORIGIN_REGEX` | Lets Cloudflare **preview** URLs (`https://<hash>.energy-supply-chain.pages.dev`) call the API. Without it, previews load but every API call is blocked. |

Run the same checks locally before pushing:

```bash
cd backend
python -m pytest -q          # uses DB_* from backend/.env

cd ../frontend
npm run typecheck
NEXT_PUBLIC_API_URL=http://127.0.0.1:9 npm run build
npx playwright install chromium   # first time only
npm run test:e2e
```

---

## 4. How each platform plugs in

### Cloudflare Pages (frontend) — already connected

The "Cloudflare Pages" check on every commit shows the Cloudflare GitHub app
is installed. For each PR, Cloudflare builds the branch and posts a **preview
URL** as a check and comment. Merging to `main` deploys production.

Check in **Cloudflare → Workers & Pages → energy-supply-chain → Settings**:

- **Build:** root directory `frontend`, build command `npm run build`, output directory `out`.
- **Variables and Secrets:** there are separate **Production** and **Preview** sets. Add `NEXT_PUBLIC_API_URL` and `NEXT_PUBLIC_CARTO_KEY` to **Preview** too. Otherwise previews fall back to `localhost:8000` and show "Backend offline".
- **Branch control:** production branch `main`; preview deployments for all other branches.

### Render (backend)

Render deploys on pushes to `main`. Two settings make it part of the pipeline:

- **Settings → Build & Deploy → Auto-Deploy → "After CI Checks Pass".** Render then waits until GitHub reports the commit's checks green before deploying, so a red `main` never reaches production.
- **Environment:** add
  `CORS_ORIGIN_REGEX = ^https://([a-z0-9-]+\.)?energy-supply-chain\.pages\.dev$`
  so preview frontends can reach the API. `CORS_ORIGINS` stays as the production origin.

Render also offers per-PR preview environments, but that depends on your plan.
On the free tier, previews point at the production API, which is fine for UI work.

### Neon (database) — a database branch per PR

A Neon **branch** is a copy-on-write clone of your database: it starts with
production's exact schema and data, takes about a second to create, and costs
almost nothing until it diverges. `backend-ci.yml` uses that to give each PR
its own database:

```
PR #42 opened ─► create branch ci/pr-42 (clone of main) ─► pytest against it
push again    ─► reuse ci/pr-42                         ─► pytest again
PR closed     ─► neon-cleanup.yml deletes ci/pr-42
```

Production is never touched. Tests also roll back every transaction, so the
branch stays clean between runs. Each branch suspends after 5 idle minutes,
so it doesn't burn compute hours, and expires after 7 days even if cleanup is
missed.

**Setup (one time):**

1. Neon Console → Account settings → **API keys** → create a key.
2. GitHub → Settings → **Secrets and variables → Actions**:
   - **Secrets** tab → `NEON_API_KEY` = the key
   - **Variables** tab → `NEON_PROJECT_ID` = your project ID (Neon → Project settings)
   - Optional variables if yours differ from Neon's defaults:
     `NEON_DATABASE` (default `neondb`), `NEON_ROLE` (default `neondb_owner`),
     `NEON_PARENT_BRANCH` (default: the project's primary branch).

> **Known issue:** branch creation currently returns HTTP 412 and CI falls
> back to the container (see `TECHNICAL_DEBT.md`). The job summary says which
> database a run used.

**Until those exist, and always for forked or Dependabot PRs** (GitHub never
gives them secrets), backend CI uses a throwaway Postgres container instead.
The check still runs; it just doesn't use production-like data. The job
summary says which database a run used.

> Free plan note: branches count toward your Neon branch limit, which is why
> cleanup + expiry matter. If you have many PRs open at once, close stale ones.

---

## 5. Bots worth adding

| Bot | What it does | How to add |
|---|---|---|
| **Cloudflare Pages** | Preview URL per PR | Already installed |
| **Dependabot** | Upgrade PRs (config in this repo) plus vulnerability alerts | Settings → Code security → enable *Dependabot alerts* and *Dependabot security updates* |
| **CodeQL** | Security findings on the PR diff | Workflow in this repo; results under Security → Code scanning |
| **AI code reviewer** | Reads every PR and leaves line comments | Choose one:<br>• **Claude:** in a `claude` terminal in this repo, run `/install-github-app`. It installs the Claude GitHub app and adds a workflow. Needs an Anthropic API key, stored as a repo secret.<br>• **CodeRabbit:** install the CodeRabbit GitHub app from the Marketplace; free for public repos. |

Bot comments are suggestions, not orders. You decide what to apply.

---

## 6. Protect `main` (one-time, in GitHub settings)

**Settings → Rules → Rulesets → New branch ruleset**

- Name: `main`, Enforcement: **Active**, Target: **Default branch**
- ✅ Restrict deletions
- ✅ Block force pushes
- ✅ Require a pull request before merging
  - Required approvals: **0** for now. GitHub doesn't let you approve your own PR, so with 1 required approval a solo maintainer can never merge. Raise it to 1 when a collaborator joins.
- ✅ Require status checks to pass
  - Add `verify` (Frontend CI) and `test` (Backend CI). They only appear in the picker **after the workflows have run once**, so do this after the first PR.
  - Optionally add `Cloudflare Pages`.
- Bypass list: add yourself (Repository admin) as an escape hatch. Use it rarely.

---

## 7. Hands-on: a PR from start to finish

```bash
git switch main && git pull
git switch -c fix/short-name
# …edit…
cd backend && python -m pytest -q
cd ../frontend && npm run typecheck && npm run test:e2e
git add <files>               # never .env; check `git status` first
git commit -m "fix: what changed"
git push -u origin fix/short-name
gh pr create --base main --fill
```

Then watch the parts connect:

1. **Checks tab:** `verify`, `test`, two `CodeQL` jobs and `Cloudflare Pages`
   start. A failing step's log: `gh run view --log-failed`.
2. **Cloudflare's comment:** open the preview URL and click through.
3. **Review:** Files changed → line comments → Finish your review.
4. **Merge** when green. Cloudflare deploys production; Render deploys after
   CI if `backend/` changed.

### Stacked PRs (one PR built on another)

If PR B branches from PR A, set B's base to A's branch so its diff shows only
its own commits. **Merge A without deleting its branch first**, or retarget B
to `main` before deleting it: GitHub *closes* a PR whose base branch is
deleted rather than retargeting it, and a closed PR with a deleted base cannot
be reopened. (That is how #33 became #34.)

### Dependabot PRs

They run the same checks. Bot comments such as `@dependabot rebase` work, but
a closed Dependabot PR plus an `ignore` rule in `dependabot.yml` is the durable
way to hold back a breaking upgrade.

Useful `gh` commands:

```bash
gh pr status                 # your PRs and their check state
gh pr checks <n> --watch     # wait for a PR's checks
gh run list --limit 5        # recent workflow runs
gh run view --log-failed     # logs of the failing step
gh pr merge <n> --merge --delete-branch
```

---

## 8. Day-to-day loop after this

```
git switch main && git pull
git switch -c fix/short-name
…edit… npm run typecheck && npm run test:e2e
git commit -am "fix: what changed"
git push -u origin fix/short-name
gh pr create --fill
→ checks + preview + bot review → merge → auto-deploy
```

Small PRs (one idea each) review faster, fail CI less, and are easy to revert.
