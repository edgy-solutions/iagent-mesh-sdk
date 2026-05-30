# iagent-mesh-sdk (DevEx Hub)

This repository serves as the Data-Driven Developer Experience (DevEx) Hub and provides the `iagent_mesh` SDK core library, which includes universal contracts and an infrastructure wrapper for the iagent Mesh platform.

> 📖 **Architectural Guide:** Read [Launch Domain Nodes, Not Scripts](docs/architecture_manifesto.md) to understand why this framework is required for enterprise AI deployments.

## Architecture & Features

This Hub leverages the **Inception Pattern** to dynamically scaffold new agent tools.

- **`iagent_mesh` Core Library**: Contains `MeshTool` for routing, FastAPI execution, and Topaz Zero-Trust security.
- **Templates**: Standardized data scientist environments (Pure Math, Instructor + Polars, BAML + Pandas).
- **Interactive Scaffolding**: Use `scripts/scaffold.sh` to locally generate a new agent from a template.
- **MCP Server**: The `mcp_server/server.py` exposes tools (`scaffold_local_workspace`, `publish_local_to_mesh`) for intelligent IDE-based agent creation.
- **Cloud Endpoints**: `app.py` exposes REST APIs (`scaffold_generator`, `mesh_publisher`) for the central orchestrator to provision workspaces dynamically.

## Environment Configuration

This SDK relies on centralized environment variables for all integrations to ensure no hardcoded enterprise strings are checked in. See the `.env.example` file in the root directory for a full list.

**Required URLs:**
- `GIT_PROVISION_API_URL`: The platform provisioning API for repositories.
- `GIT_SERVER_HOST`: The core Git server hostname.
- `ARTIFACTORY_BASE_URL`: The enterprise artifact repository.

**Optional URLs / tokens (only needed if `MESH_REGISTER_ON_STARTUP=true`):**
- `DATAHUB_GMS_URL`: The DataHub GMS endpoint the SDK pushes registrations to.
- `DATAHUB_TOKEN`: Bearer token for the GMS emitter.

**Required Tokens (Depending on deployment):**
- `PLATFORM_GIT_TOKEN`: Used by the cloud pod (`app.py`) for live git publishing.
- `MESH_DEV_TOKEN`: Used by the local `mcp_server` to authenticate against provisioning APIs.

## Installation & Testing

Data scientists can install the core SDK via:
```bash
uv pip install git+https://[your-repo-url]
```

To run the robust regression testing suite:
```bash
uv pip install -e ".[dev]"
python -m pytest
```
