# StormLead MCP Profiles

This directory stores Docker MCP Toolkit profile exports used by `opencode.json` and `.codex/config.toml`.

Import the profiles on a new machine before starting OpenCode or Codex in this repo:

```powershell
docker mcp profile import .docker/mcp-profile-docker.json
docker mcp profile import .docker/mcp-profile-kubernetes.json
```

Optional local configuration:

```powershell
docker mcp profile config stormlead_docker --set dockerhub.username=<dockerhub-username>
docker mcp profile config stormlead_kubernetes --set kubernetes.config_path=$env:USERPROFILE\.kube\config
```

Secrets and credentials stay in Docker Desktop's local secret store and are not stored in these files.

OpenCode reads `opencode.json`. Codex reads `.codex/config.toml` after this project is trusted.
