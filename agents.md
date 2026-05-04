# AI Agents Overview

This document outlines the design and architecture of AI agents built using the `iagent_mesh` SDK.

## Key Principles

1. **Focus on Business Logic**: Agents should focus purely on analytical or mathematical business logic. Infrastructure, routing, authentication (Topaz), and discovery (DataHub) are handled by the SDK wrapper.
2. **Data Gravity**: Agents run close to the data, fetching secure short-lived STS tokens provided by Engine DA to read large datasets efficiently (e.g. Polars direct from MinIO).
3. **Structured Outputs**: Agents define precise Pydantic schemas for Inputs and Outputs to allow predictable interaction with LLMs and other services.

## The DevEx Hub

The `iagent-mesh-sdk` has been upgraded into a Data-Driven Developer Experience Hub.
Agents are no longer created from scratch. Instead, they are dynamically scaffolded using the Hub's built-in templates (e.g. `02_instructor_polars`, `03_baml_pandas`).

This scaffolding can be triggered manually via `scripts/scaffold.sh`, automatically inside the IDE via the MCP Server (`mcp_server/server.py`), or through the cloud orchestrator endpoints in `app.py`.
