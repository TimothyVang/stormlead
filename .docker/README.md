# StormLead MCP Profiles

This directory stores Docker MCP Toolkit profile exports used by `opencode.json`.

Import the profiles on a new machine before starting OpenCode in this repo:

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
