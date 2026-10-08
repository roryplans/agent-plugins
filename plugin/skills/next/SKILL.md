---
name: next
description: Pull and execute the next queued RoryPlans dispatch task for this agent, then report the result. Runs exactly one task cycle.
argument-hint: [agentId]
---

# Pull and execute the next RoryPlans task

Run exactly one RoryPlans dispatch task cycle:

1. Verify the RoryPlans MCP tools are reachable. In Claude Code, if the tools are deferred, load them first: ToolSearch on the RoryPlans MCP for `get_next_task`, `complete_task`, and `fail_task`. If the server is not connected or returns 401/Unauthorized, stop and tell the user: the `RORYPLANS_MCP_TOKEN` environment variable is likely missing or expired — run the plugin's `setup` command to configure it (or see the plugin README).
2. Determine the agent ID: use `$ARGUMENTS` if provided; otherwise the default for this platform — `claude-code` when running in Claude Code, `codex` when running in Codex.
3. Call `get_next_task` with `{ "agentId": "<agent id from step 2>" }`.
4. If no task is returned, report "no pending tasks for <agentId>" and stop. Do not invent work.
5. Execute the prompt returned by `get_next_task` in this environment (repo, tools, browser if available).
6. Verify the work actually succeeded (run tests, check output — whatever the task calls for).
7. Usage report: in Claude Code, skip this step — the plugin's hook adds `usage` to the next call itself, so do not run `usageReporting.command` and do not pass `usage`. In Codex: if the `get_next_task` response included a `usageReporting.command`, run it exactly as given, right before the next step (success or failure). It reads only token counts and model names from this session's local transcript and prints one JSON line. If that line has `"models"`, pass the whole object unchanged as `usage` in the next step; if it has `"error"`, the command fails, or you cannot run shell commands, omit `usage`. Never estimate or invent token counts or costs.
8. On verified success: call `complete_task` with that `taskId`, the output, a real summary of what was done, and `usage` from step 7 when you have it.
9. If blocked or the work cannot be completed: call `fail_task` with that `taskId`, a clear reason, and `usage` from step 7 when you have it.
10. Stop and report the outcome to the user. One task per cycle — do not pull another task.
