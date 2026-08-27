---
name: tasks
description: List pending RoryPlans dispatch tasks for this agent in a readable summary.
argument-hint: [agentId]
disable-model-invocation: true
---

# List pending RoryPlans tasks

1. Verify the RoryPlans MCP tools are reachable. In Claude Code, if the tools are deferred, load them first: ToolSearch on the RoryPlans MCP for `list_pending_tasks`. If the server is not connected or returns 401/Unauthorized, stop and tell the user: the `RORYPLANS_MCP_TOKEN` environment variable is likely missing or expired — run the plugin's `setup` command to configure it (or see the plugin README).
2. Determine the agent ID: use `$ARGUMENTS` if provided; otherwise the default for this platform — `claude-code` when running in Claude Code, `codex` when running in Codex.
3. Call `list_pending_tasks` with `{ "agentId": "<agent id from step 2>" }`.
4. Present the result as a readable summary: for each task show its id, plan, title, and status. If there are none, say "no pending tasks for <agentId>".
5. Do not claim, execute, or modify any task — this command is read-only.
