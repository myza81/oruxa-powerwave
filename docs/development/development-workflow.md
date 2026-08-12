# Powerwave Development & Deployment Workflow

This is the plain-English reference for how code moves from your laptop to a
real, working environment. It exists so you don't have to re-derive the
process from memory each time — read it whenever you're unsure "what comes
next."

It documents the workflow **as it exists today** for Powerwave, and is
intended to apply to future Oruxa applications too.

For *why* the infrastructure is shaped the way it is (portability, data
ownership, etc.), see
[docs/architecture/oruxa-architecture.md](../architecture/oruxa-architecture.md).
This document is about the day-to-day *process*, not the architecture
reasoning.

---

## 1. Overall workflow

```text
Local VS Code
     ↓
feature/fix/docs branch
     ↓
push to GitHub
     ↓
CI tests
     ↓
Pull Request
     ↓
merge to main
     ↓
deploy main to DEV
     ↓
test / UAT in DEV
     ↓
if approved, deploy the SAME commit to PROD
```

Nothing is automatic past "merge to main." Deploying to DEV and deploying to
PROD are both manual, deliberate actions you trigger yourself in GitHub
Actions.

---

## 2. What each layer is for

| Layer | Role |
|---|---|
| **Local development** | Where you write and manually try out code, on your own machine. |
| **Git branch** | An isolated line of change so your work-in-progress doesn't disturb `main`. |
| **GitHub** | The single source of truth for the code. Nothing is "real" until it's on GitHub. |
| **CI** | Automatically runs tests on every push, so broken code is caught before it can be merged or deployed. |
| **Pull Request (PR)** | A review checkpoint before code enters `main`. |
| **`main` branch** | The one line of history that DEV and PROD are ever deployed from. |
| **DEV environment** | A real, running, browser-accessible copy of the app used to prove things actually work. |
| **PROD environment** | The environment real users and real data depend on. |

A few points worth being explicit about, because they're easy to blur
together when you're still building intuition for this:

- **A Git branch is not an environment.** A branch only organizes *code* —
  it doesn't run anywhere, doesn't have a database, and doesn't prove
  anything works. It just keeps one line of change separate from another.
- **DEV is a real running environment**, with its own containers, its own
  database, and its own storage. It's where you actually click through the
  app and confirm it behaves correctly — a branch existing does not tell you
  that.
- **A Git branch does not replace a DEV environment**, and a DEV environment
  does not replace Git branches. They solve different problems: branches
  isolate code changes; DEV proves the code works when actually run.
- **PROD is for stable releases only.** It holds real user data, so nothing
  reaches PROD without first being proven in DEV.

---

## 3. Branch naming convention

Keep it simple and descriptive:

```text
feature/<short-name>
fix/<short-name>
docs/<short-name>
```

Examples:

```text
feature/comtrade-sync
feature/calculated-signals
fix/excel-import
docs/update-architecture
```

Use `feature/` for new functionality, `fix/` for bug fixes, and `docs/` for
documentation-only changes.

---

## 4. Starting a new piece of work

Always branch off an up-to-date `main`:

```bash
git checkout main
git pull
git checkout -b feature/<name>
```

This makes sure your branch starts from the latest merged code, not from
whatever was on your machine last week.

---

## 5. Before committing

Two commands to get in the habit of running before every commit:

```bash
git status
```

Shows *what* you've changed — which files are modified, added, or untracked.
Use it to catch anything unexpected (a stray file you didn't mean to touch,
or a file you forgot to add).

```bash
git diff
```

Shows the *actual line-by-line changes*. Use it to review your own work
before it becomes a commit — it's much easier to catch a mistake here than
after it's pushed.

---

## 6. Commit and push

```bash
git add .
git commit -m "feat: improve COMTRADE synchronization"
git push -u origin feature/comtrade-sync
```

Write commit messages that describe *what* changed, briefly. The `-u` on
the first push links your local branch to the remote one, so future
`git push`/`git pull` on this branch don't need the branch name repeated.

---

## 7. Pull Request (PR) workflow

Even working solo, open a PR before merging into `main`. It gives you one
last structured checkpoint to review your own change with fresh eyes, and it
creates a record of *why* the change happened — not just what changed.

Before merging, check:

- **What changed** — a clear summary of the change.
- **Why it changed** — the reason or problem being solved.
- **Tests passed** — CI is green.
- **Unexpected impact** — did this touch anything outside the intended
  scope?
- **Architecture / data / security impact**, where relevant — does this
  affect the database, storage, an API boundary, or how data flows between
  environments? If so, has the [change governance](#14-change-governance)
  process in section 14 been followed?

Only merge once you can answer all of these.

---

## 8. DEV deployment

Current DEV environment:

| | |
|---|---|
| Frontend | `https://dev.powerwave.oruxa.uk` |
| API | `https://api.dev.powerwave.oruxa.uk` |
| VPS checkout | `/srv/oruxa/apps/powerwave-dev` |
| Database | `powerwave_dev_db` |
| Storage | `/srv/oruxa/data/powerwave-dev` |
| Backend port | `8200` |
| Frontend port | `8201` |

> **Note:** the DNS names, and the exact DEV database name/credentials, are
> configured outside this repository (VPS Caddy config and database
> provisioning). The VPS checkout path and ports *are* enforced by the repo
> (`compose.dev.yaml`, and the `VPS_APP_PATH` GitHub Environment variable —
> see [section 13](#13-deployment-safety-rule)). If any value above no
> longer matches reality, fix this document rather than trusting it blindly.

To deploy:

```text
GitHub
  → Actions
  → Deploy Powerwave
  → Run workflow
  → target = dev
```

This runs the backend test suite first, then deploys whichever commit you
pick (defaults to the branch you run it from — normally `main`).

---

## 9. DEV verification

After a DEV deployment, check the basics first:

```bash
curl https://api.dev.powerwave.oruxa.uk/health
curl -I https://dev.powerwave.oruxa.uk
```

These only confirm the containers are up and responding — they do **not**
confirm the feature you changed actually works. After the health check
passes, do functional/UAT testing: open the app in a browser and manually
exercise the feature you changed, plus anything nearby it could have
affected. A green health check is the minimum bar, not the finish line.

---

## 10. PROD deployment

Current PROD environment:

| | |
|---|---|
| Frontend | `https://powerwave.oruxa.uk` |
| API | `https://api.powerwave.oruxa.uk` |
| VPS checkout | `/srv/oruxa/apps/powerwave` |
| Database | `powerwave_db` |
| Storage | `/srv/oruxa/data/powerwave` |
| Backend port | `8100` |
| Frontend port | `8101` |

To deploy:

```text
GitHub
  → Actions
  → Deploy Powerwave
  → Run workflow
  → target = prod
```

Only deploy to PROD once the same commit has already been verified in DEV
(see next section).

---

## 11. Important release principle: same commit, DEV then PROD

The whole point of testing in DEV is that PROD gets the *exact same,
already-proven* code — not a re-build, not "basically the same thing."

```text
DEV  → abc123
PROD → abc123
```

Both the "Deploy Powerwave" workflow's `dev` and `prod` targets deploy by
Git commit SHA (`git checkout --detach <sha>` on the VPS), so this is
mechanical, not something you have to remember to enforce by hand — but it's
still up to you to pick the commit that was actually tested in DEV when you
trigger the PROD deployment, rather than re-running from a newer `main`.

This gives traceability: at any point you can say exactly which commit is
running in PROD, and know it's the same one someone already verified in DEV.

---

## 12. Environment isolation

DEV and PROD must stay completely separate in every dimension:

- containers (separate Compose project names: `powerwave-dev` /
  `powerwave-prod`)
- ports (`8200`/`8201` vs `8100`/`8101`)
- database (`powerwave_dev_db` vs `powerwave_db`)
- storage (`/srv/oruxa/data/powerwave-dev` vs `/srv/oruxa/data/powerwave`)
- environment variables / configuration

**DEV must never accidentally read or write PROD data.** This isolation is
largely enforced by the Compose overlays (`compose.dev.yaml` /
`compose.prod.yaml`) and is checked in CI (`.github/workflows/ci.yml`
verifies DEV and PROD render as isolated Compose projects with non-
overlapping ports and image tags). Don't work around it by hand-editing
config on a host — see [section 14](#14-change-governance).

---

## 13. Deployment safety rule

Deployment configuration must **fail safely** when something required is
missing — never silently fall back to a default that could point at the
wrong environment.

Concretely: `VPS_APP_PATH` must be explicitly configured per GitHub
Environment. The deploy workflow
([.github/workflows/deploy.yml](../../.github/workflows/deploy.yml)) checks
this before doing anything else, and refuses to proceed if it's unset.

Current intended mapping:

```text
GitHub Environment: dev
VPS_APP_PATH=/srv/oruxa/apps/powerwave-dev

GitHub Environment: prod
VPS_APP_PATH=/srv/oruxa/apps/powerwave
```

The rule this protects: **DEV must never silently fall back to a PROD path**
(or vice versa). If the variable isn't set for an environment, the
deployment must fail loudly, not guess.

---

## 14. Change governance

Before changing existing behavior, workflow, or architecture that seems
incorrect or suboptimal — don't just change it. First:

1. Understand how the current code actually works.
2. Identify the issue.
3. Gather evidence.
4. Describe the proposed solution.
5. Explain the benefits.
6. Explain the risks.
7. Explain the expected impact.
8. Get approval before implementing.

In short: **don't assume existing behavior is wrong, and don't change it
without review** — even if it looks odd at first glance. There's often a
reason, and if there isn't, this process is how that gets surfaced safely.

---

## 15. Keep the workflow practical

Powerwave and future Oruxa apps deliberately avoid unnecessary complexity —
no Kubernetes, no service mesh, no long chain of staging tiers, no
infrastructure that isn't already in use.

The guiding principle:

> **Professional enough to be correct.**
> **Simple enough for one person to manage.**
> **Flexible enough to grow later.**

If a proposed change adds infrastructure or process weight without solving
a real, current problem, that's a signal to slow down and question it
before adopting it.

---

## 16. Daily quick reference

**Start:**

```bash
git checkout main
git pull
git checkout -b feature/<name>
```

**Work and review:**

```bash
git status
git diff
```

**Commit:**

```bash
git add .
git commit -m "..."
git push -u origin <branch>
```

**Then:**

```text
Open PR
  → CI passes
  → merge to main
  → deploy DEV
  → test DEV
  → deploy same approved commit to PROD
```
