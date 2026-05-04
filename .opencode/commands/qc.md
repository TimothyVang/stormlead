---
description: Quick commit + auto-push
---

# qc - quick commit + auto-push

Perform a portable, project-agnostic quick commit and push flow.

## Two Invocations

- `/qc` commits and pushes the current branch to its upstream on origin. This is the default for normal feature-branch work.
- `/qc main` switches to the repo default branch, commits there, and pushes directly to origin's default branch. Use this solo-speed flow only when the user is the only reviewer and the change is ready.

If `/qc main` is invoked while on a feature branch with uncommitted changes, carry the changes across with `git stash --include-untracked`, checkout the detected default branch, then `git stash pop`. If conflicts cannot be resolved cleanly, stop and surface the conflict to the user. Do not throw away work.

## Hard Rules

- Never use `--no-verify`.
- Never use `--no-gpg-sign`.
- Never use `git commit --amend`.
- Never use `--allow-empty` unless explicitly requested.
- Never force-push or use `--force-with-lease`.
- Never edit git config or set committer identity.
- Never add AI attribution lines, AI coauthor trailers, or equivalent AI watermarks.
- Never stage likely secrets or junk without asking first, including `.env`, `.env.*`, credentials, keys, large binaries, `node_modules`, `__pycache__`, build outputs, and unfamiliar generated files.

## Step 0 - Verify GitHub CLI When Needed

Before staging anything, verify whether pushing will work:

```bash
command -v gh >/dev/null && gh auth status >/dev/null 2>&1
```

If this fails, inspect the remote URL. If the remote is SSH and normal `git push` credentials are likely handled by SSH, continue carefully. If the remote is GitHub HTTPS and `gh` is missing or unauthenticated, bootstrap before committing.

Install `gh` only with the matching platform command and only when appropriate:

- Ubuntu or Debian: install with the official GitHub CLI apt repository.
- macOS: `brew install gh`.
- Fedora, RHEL, or CentOS Stream: `sudo dnf install -y gh`.
- Arch: `sudo pacman -S --noconfirm github-cli`.
- Alpine: `sudo apk add github-cli`.
- Windows: `winget install --id GitHub.cli`.
- Other or unknown: point the user to `https://cli.github.com/` and stop.

Then authenticate:

```bash
gh auth login --hostname github.com --git-protocol https --web
```

For headless hosts, use:

```bash
gh auth login --hostname github.com --git-protocol https
```

Verify after auth:

```bash
gh auth status
git push --dry-run
```

If auth or dry-run still fails, stop and surface the failure. Do not create a commit that cannot be pushed unless the user explicitly chooses to commit without pushing.

## Step 1 - Inspect The Working Tree

Run git status, diff, staged diff, and recent log before drafting any message:

```bash
git status
git diff --stat
git diff
git diff --cached
git log -5 --oneline
```

Look for files the user may not have meant to commit, mixed unrelated concerns, and the repo's commit-message style.

If there are no changes, do not create an empty commit. Tell the user there is nothing to commit.

## Step 2 - Detect Project Conventions

Before drafting the message, check for project-specific rules in this order and stop at the first hit:

1. `AGENTS.md` at repo root.
2. `CONTRIBUTING.md`.
3. `.gitmessage` or `commit.template` in `.git/config`.
4. Recent commit log.

Match the dominant style:

- `type(scope): summary` means Conventional Commits.
- `JIRA-123: summary` means ticket-prefixed commits.
- Plain imperative one-liners mean freeform imperative style.

If a task ID is required, resolve it from the user's request, recent commits, or project planning files. If still unresolved, ask before defaulting.

## Step 3 - Stage Safely

Prefer named-path staging:

```bash
git add path/to/file.py path/to/other.md
```

Use `git add -A` or `git add .` only if both are true:

- The user explicitly said to stage everything or all changes.
- `git status` shows no unexpected files, secrets, caches, build outputs, or large unfamiliar additions.

If the diff contains obviously unrelated concerns, split them into separate commits. State the split plan before staging the first commit.

## Step 4 - Draft The Commit Message

Draft one concise message in imperative voice, focused on why the change is being made.

Default to Conventional Commits if no project convention is detected:

```text
<type>(<scope>): <summary>
```

Use these types:

- `feat` for a new user-visible capability.
- `fix` for a behavior bug fix.
- `test` for test-only changes.
- `chore` for tooling, config, dependency, or maintenance changes.
- `docs` for documentation-only changes.
- `refactor` for no-behavior cleanup.
- `perf` for performance-only changes.
- `style` for formatting-only changes.
- `ci` for CI changes.
- `build` for build-system changes.
- `revert` for reverts.

Keep the summary near 70 characters when possible. Add a body only when the reason is non-obvious.

Forbidden commit-message content:

- AI attribution or watermark lines.
- Vague messages like `update files`, `misc changes`, or `changes`.

State the drafted message to the user before committing if there is any ambiguity. If the changes are straightforward and the user requested `/qc`, proceed without asking unless a safety rule requires user input.

## Step 5 - Commit

Commit normally:

```bash
git commit -m "<message>"
```

Let hooks and signing run normally. Do not bypass them.

If a pre-commit or commit-msg hook fails, read the failure output. If the issue is clearly caused by the current changes, fix it with the smallest correct change, restage the fix, and create a normal new commit. Since the failed commit did not happen, never amend. If the hook fails repeatedly on the same issue, stop and root-cause rather than looping.

If the user asks to bypass hooks, refuse. Explain that bypassing hooks overrides a project rule and they should run the bypass manually if they intentionally want it.

## Step 6 - Push

If the branch already tracks an upstream, plain push is fine:

```bash
git push
```

Otherwise push and set upstream:

```bash
git push -u origin HEAD
```

For `/qc main`, push the detected default branch:

```bash
git push origin <default-branch>
```

If push is rejected as non-fast-forward, blocked by branch protection, or otherwise fails, stop and surface the exact error. Do not force-push.

## Failure Modes

Stop and ask or report clearly when:

- The working tree contains files that may be secrets, large binaries, generated junk, or unintended additions.
- No commit-message convention is detectable and recent commits are unavailable.
- A required task ID cannot be resolved.
- Stash pop for `/qc main` conflicts.
- Hooks fail repeatedly on the same issue.
- `gh` auth or `git push --dry-run` fails after bootstrap.
- Push is rejected.

## Final Response

After completion, report concisely:

- Commit hash and message.
- Files committed or number of files changed.
- Push target.
- Any warnings or follow-up needed.
