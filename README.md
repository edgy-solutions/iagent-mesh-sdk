# iagent-mesh-sdk (DevEx Hub)

This repository serves as the Data-Driven Developer Experience (DevEx) Hub and provides the `iagent_mesh` SDK core library, which includes universal contracts and an infrastructure wrapper for the iagent Mesh platform.

## Architecture & Features

This Hub leverages the **Inception Pattern** to dynamically scaffold new agent tools.

- **`iagent_mesh` Core Library**: Contains `MeshTool` for routing, FastAPI execution, and Topaz Zero-Trust security.
- **Templates**: Standardized data scientist environments (Pure Math, Instructor + Polars, BAML + Pandas).
- **Interactive Scaffolding**: Use `scripts/scaffold.sh` to locally generate a new agent from a template.
- **MCP Server**: The `mcp_server/server.py` exposes tools (`scaffold_local_workspace`, `publish_local_to_mesh`) for intelligent IDE-based agent creation.
- **Cloud Endpoints**: `app.py` exposes REST APIs (`scaffold_generator`, `mesh_publisher`) for the central orchestrator to provision workspaces dynamically.

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
