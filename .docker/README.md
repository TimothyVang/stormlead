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

Default profiles are inspect-first and local/dev only. The Docker Hub profile keeps mutating repository tools out of the default allowlist; the Kubernetes profile keeps apply/create/delete/patch/Helm/exec/scale tools out of the default allowlist. Do not configure Docker Hub PATs or production kubeconfigs for these profiles without explicit approval.

Ask before any Docker/Kubernetes action that mutates state, including Docker Hub repository changes, deleting containers/volumes/images, changing kube contexts, applying manifests, installing Helm charts, or deleting namespaces/clusters.

OpenCode reads `opencode.json`. Codex reads `.codex/config.toml` after this project is trusted.
