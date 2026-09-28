"""``iagent_mesh.writers`` — concrete implementations that hold a driver.

DELIBERATELY separate from ``iagent_mesh.interfaces``, whose own module docstring bans importing
a driver — ``httpx`` is named there explicitly. ``httpx>=0.24.0`` is already a HARD dependency of
this distribution (declared in ``pyproject.toml``, already imported by
``mcp_server/mesh_explain.py``), so the question this split answers is never "can httpx be
avoided" — it already ships with every install of this package — the question is "which modules
may IMPORT it", and the answer stays no for ``interfaces.py`` and yes here, where the ONE
reference implementation this SDK ships lives.

The dependency runs one direction only: this package imports ``iagent_mesh.interfaces`` (the
Protocols it implements, ``Initiator``, ``MeshWriteResult``); nothing under ``iagent_mesh.
interfaces`` imports this package. A consumer who never imports ``iagent_mesh.writers`` never
loads a line of this module — the Protocols alone are enough to write an implementation of their
own, which is the whole point of shipping a contract separately from an implementation of it.
"""
