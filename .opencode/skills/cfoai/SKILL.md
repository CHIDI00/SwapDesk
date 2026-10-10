---
name: cfoai
description: Connect the cfo.ai MCP server, authenticate, select workspace, and work safely with financial models. Use when user mentions cfo.ai, cfoai MCP, financial model, workspace, org_id, table blocks, or canvas blocks.
---

# cfo.ai agent skill

Help the user connect the cfo.ai MCP server, complete browser-based authentication, select the correct workspace, and work safely with live financial Models.

Source of truth: read https://docs.cfo.ai/agent-instructions.md first, plus https://docs.cfo.ai/llms.txt to discover related pages.

## Setup (already configured in this project)

Production MCP URL: `https://api.cfo.ai/mcp`, registered as `cfoai` in `opencode.json` as a remote MCP server.

- Confirm the user can sign in at https://app.cfo.ai. Direct them to create an account / complete setup in the browser if not.
- Never ask for password, verification code, payment details, or tokens.
- Auth is browser-based OAuth. If tools report auth errors or `cfoai` is missing, restart the session and follow the client's normal remote-MCP authorization flow.

## Verify workspace

- Confirm the client lists `cfoai` and exposes its tools.
- If the user has more than one workspace, call `list_orgs` and pass the intended workspace ID/slug as `org_id` on subsequent calls.
- Verify with a read-only inspection call before reporting success.

## Work safely with the Model

- Read the MCP-provided modeling instructions at initialization.
- Before creating/changing logic: call `inspect_skills` (`list` block) to find the `build-model` skill, then its `instructions` block. Use `inspect_pages`, `inspect_table_blocks`, `inspect_dimension_mappings`, `inspect_scenarios` to understand existing state.
- Mental model: workspace holds Model, Pages, Scenarios, Variables, Dimensions. Main is the primary Scenario.
- `edit_table_blocks` writes all model formulas; `edit_pages`, `edit_dimension_mappings`, `edit_scenarios` change pages/mappings/scenarios; `inspect_canvas_library` + `edit_canvas_blocks` handle Canvas visuals.
- Writes apply to the live Model — match the user's request and workspace access.
- Shape each multi-action tool call as exactly one named action block (e.g. `{ "read": { "target": "..." } }`), no flat `action` field. Copy names and `Name#hex` refs from inspection results.
