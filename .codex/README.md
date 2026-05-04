# Codex Setup

This directory makes the repo's MCP setup usable by Codex CLI and the Codex IDE extension.

Codex loads `.codex/config.toml` only for trusted projects. The config starts the same local MCP servers used by `opencode.json`:

- `stormlead` local ops MCP from `tools/mcp/stormlead-local-ops.mjs`
- `stormlead_docker`
- `stormlead_kubernetes`

## One-Time Setup

Install npm dependencies so the repo-local Codex CLI is available through `npm run codex:*` scripts:

```powershell
npm install
```

Import the Docker MCP Toolkit profiles before starting Codex in this repo:

```powershell
docker mcp profile import .docker/mcp-profile-docker.json
docker mcp profile import .docker/mcp-profile-kubernetes.json
```

Optional local-only configuration:

```powershell
docker mcp profile config stormlead_docker --set dockerhub.username=<dockerhub-username>
docker mcp profile config stormlead_kubernetes --set kubernetes.config_path=$env:USERPROFILE\.kube\config
```

## Verify

```powershell
npm run validate:codex
npm run codex:version
npm run codex:mcp:list
npm run mcp:stormlead:smoke
```

Codex project config is loaded after the project is trusted. If `npm run codex:mcp:list` reports no MCP servers, start `npm run codex` once and trust this workspace.

Inside the Codex TUI, use `/mcp` to inspect active MCP servers.

## Repo Commands

```powershell
npm run codex
npm run codex:readonly
npm run codex:exec -- "Review the current diff"
npm run codex:review
npm run codex:login
```

Use `npm run codex` for normal local work. Use `npm run codex:readonly` for inspection-only sessions. Use `npm run codex:exec -- "<prompt>"` for non-interactive automation. Use `npm run codex:review` for a local Codex review of uncommitted changes.

## Safety

- The MCP servers are optional (`required = false`) so Codex can still start when Docker Desktop or profiles are unavailable.
- Interactive repo scripts use `workspace-write` with `on-request` approval by default; `codex:exec` uses sandboxed non-interactive mode with `approval_policy=never` because it cannot pause for approval.
- Do not use `--yolo` or `danger-full-access` here unless explicitly approved.
- StormLead Local Ops command tools require `confirm_synthetic_local=true` and run fixed local scripts only.
- Treat Docker and Kubernetes access as local/dev inspect-first.
- Ask before destructive or production-like actions, including deleting volumes, deleting clusters, applying manifests, or changing remote contexts.
- Secrets stay in Docker Desktop's local secret store or ignored `.env` files, not in repo config.
