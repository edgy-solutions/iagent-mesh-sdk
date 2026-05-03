# AI Agents Overview

This document outlines the design and architecture of AI agents built using the `iagent_mesh` SDK.

## Key Principles

1. **Focus on Business Logic**: Agents should focus purely on analytical or mathematical business logic. Infrastructure, routing, authentication (Topaz), and discovery (DataHub) are handled by the SDK wrapper.
2. **Data Gravity**: Agents run close to the data, fetching secure short-lived STS tokens provided by Engine DA to read large datasets efficiently (e.g. Polars direct from MinIO).
3. **Structured Outputs**: Agents define precise Pydantic schemas for Inputs and Outputs to allow predictable interaction with LLMs and other services.
