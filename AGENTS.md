# AGENTS.md — Meta Build & Project Manual

This is the portable playbook for **every** build and project. It tells both the
human and any AI agent how to work here: how the project is organized, how to
ship changes, what "done" means, and how to start new work without making a mess.

> **Using this on a new project:** copy this file to the repo root, then fill in
> the `PROJECT SPECIFICS` block at the bottom. Delete sections that genuinely
> don't apply — but be honest, most of them apply.

---

## 0. Operating principles (read first)

1. **Read before you edit.** Never modify a file you haven't read. Never invent
   APIs, fields, or filenames — verify they exist first.
2. **Smallest change that fully solves the task.** No drive-by rewrites, no
   speculative abstractions. One logical change at a time.
3. **Leave it runnable.** Every handoff must build/run. If you can't verify,
   say so explicitly.
4. **Match the codebase.** Follow existing patterns, naming, and structure over
   personal preference. One pattern per concern (one error shape, one date lib,
   one config source).
5. **No silent scope creep.** For naming/formatting/equivalent choices, just
   pick one and note it. For anything destructive or scope-expanding, ask first.

---

## 1. Project structure & file organization

- **Separate concerns into folders, not one god file.** Typical layout:
  - `core/` or `lib/` — shared, reusable helpers (no business logic specific to one feature)
  - `config/` — central config, env loading, constants, maps (single source of truth)
  - `<feature>/` — one folder per feature/report/module, self-contained
  - `tests/` — mirrors the source layout
  - entry points (`run.py`, `app.py`, `wsgi.py`, `index.ts`, …) stay at root
- **Files have a single concern.** Split a file when it mixes responsibilities,
  not just because it got long. Aim to keep files under ~500 lines.
- **Create `lib/`/shared-component folders on day one**, even if nearly empty.
  Centralize env vars, API helpers, and domain constants from the *first* file
  that needs them — not the third.
- **No grab-bag files.** Avoid `utils.ts` / `helpers.py` / `constants.py` dumping
  grounds. Colocate by concern.
- **Keep a current structure map** in `README.md` (a directory tree + one-line
  purpose per file/folder). Update it when you add or move things.

---

## 2. Git, commit & deploy workflow

> If the repo has a stricter local rule (e.g. `.cursor/rules/always-commit.mdc`),
> that rule wins. This is the portable baseline.

1. **Commit after every completed task** — a feature, fix, refactor, config
   change, docs edit. Don't wait to be reminded. Don't batch unrelated work:
   **one logical change, one commit.**
2. **Push immediately after committing.** An unpushed commit is invisible to the
   team and lost if the machine dies. (Critical when the repo lives in a synced
   folder like OneDrive/SharePoint, where `.git` can corrupt.)
3. **Honest commit messages.** Subject ≤72 chars, focused on the *why*. If it
   fixes a production failure, say so. Reference the affected
   runbook/report/module.
4. **Never `--amend` or force-push a pushed commit** unless the user explicitly
   asks in-conversation. Follow-up fix → new commit.
5. **Deploy is a separate step from commit.** If a change must be published to
   run in production (a runbook, a hosted app, a serverless function),
   committing is *not enough* — run the project's documented deploy step and
   tell the user what you deployed and where to verify.

```bash
git add -- <files>
git commit -m "<concise why-focused subject>"
git push
# then: run the project's deploy step if the change is production-facing
```

If push is rejected because remote is ahead: `git pull --rebase`, resolve,
push again.

---

## 3. Testing & verification (definition of done)

A task is **not done** until:

- [ ] The code runs / builds without new errors.
- [ ] Linter/type checks pass on the files you touched (fix lints you introduced).
- [ ] Relevant tests pass; new behavior has at least one test when the project has a test suite.
- [ ] You verified the actual behavior (ran it, hit the endpoint, checked output) — or you explicitly state what you couldn't verify and why.
- [ ] No secrets, debug prints, dead code, or commented-out blocks left behind.
- [ ] `README.md` / docs updated if structure, commands, or env vars changed.
- [ ] Committed **and pushed** (and deployed if production-facing).

Prefer fast feedback: run the narrowest test first, then widen. Don't add tests
just to inflate coverage — test real behavior and edge cases that matter.

---

## 4. Coding standards (clean code)

**Refactor scope vocabulary — interpret literally:**

| User says | Scope |
|---|---|
| "tidy" / "clean up" | Current file only. Dead code, naming, inline trivial things. |
| "refactor" | Whole feature/module: helpers, components, structure, dedupe, splits. |
| "aggressive/deep refactor" | Entire codebase, every category below. |

**Refactor categories — check all when refactoring:** duplicated logic → helpers;
duplicated UI → shared components; repeated style/class strings → tokenize;
magic values → named constants; god files → split by concern; inconsistent
patterns → pick one; dead code → delete; type/schema drift → centralize.

**Discipline rules (anti-fluff):**
- **Rule of 2** — an abstraction needs 2+ real call sites *now*, not "might be useful later."
- No wrapper components/functions under ~5 lines with no logic — inline them.
- No barrel/index files unless consolidating 5+ exports.
- If removing duplication adds more lines than it saves and the code is stable, leave it duplicated.

**On every edit:** before writing new code, scan for an existing helper, component,
constant, or class string. If one is close-but-not-quite, extend it — don't fork it.

**Comments:** explain non-obvious *intent / trade-offs / constraints* only. Never
narrate what the code does. No TODO-to-clean-up-later — clean up now or don't mention it.

**Secrets & config:** never hardcode credentials. Read from env/config; keep a
`.env.example` (or equivalent) listing every variable. Never commit `.env`,
keys, or tokens.

---

## 5. Documentation

- **`README.md` is the front door.** It must always answer: what this is, how to
  run it locally, how it's deployed, the env vars it needs, and the directory map.
  Keep it true — a stale README is worse than none.
- **`AGENTS.md` (this file)** holds the working conventions. Update it when a
  convention changes, not in a separate "notes" file.
- **Runbooks for operational steps.** Anything a human must do by hand (deploy,
  rotate a secret, re-run a failed job) gets a short, copy-pasteable runbook —
  in `README.md`, a `docs/` file, or a Cursor rule — with the *why*, not just the *how*.
- **Document the gotcha, not the obvious.** Capture the thing that burned you
  (e.g. "production ran old code for 3 weeks because the runbook wasn't republished").

---

## 6. Scoping new work (before writing code)

Before any non-trivial change:

1. **Restate the goal** in one sentence and the definition of done.
2. **Locate the blast radius** — which files/modules are involved? Read them.
3. **Check for prior art** — is there an existing helper/pattern/feature that
   already does most of this?
4. **Pick the approach** — if there are real trade-offs (storage, auth, sync,
   architecture), surface options and decide deliberately; otherwise just proceed.
5. **Plan in steps** — for multi-step work, write a short task list and work it
   top to bottom. Don't end the turn with steps unfinished.

If the task is ambiguous or large, plan first and confirm direction before
committing to an approach. If it's small and clear, just do it.

---

## PROJECT SPECIFICS — fill in per repo

> Everything above is portable. This block is what makes the copy *this* project's.

- **What this project is:** <one or two sentences>
- **Primary language / runtime:** <e.g. Python 3.10, Node 20>
- **Run locally:** `<command>`
- **Run tests:** `<command>`
- **Lint / typecheck:** `<command>`
- **Deploy target(s):** <name> → `<deploy command>` (who/what consumes it)
- **Secrets / env:** <where they live; never commit them>
- **Project-specific gotchas:** <the things that have broken before>
- **Local rules that override this file:** <e.g. `.cursor/rules/*.mdc`>
