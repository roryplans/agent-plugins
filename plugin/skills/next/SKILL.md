---
name: next
description: Pull and execute the next queued RoryPlans dispatch task for this agent, then report the result. Runs exactly one task cycle.
argument-hint: [agentId]
---

# Pull and execute the next RoryPlans task

Run exactly one RoryPlans dispatch task cycle:

1. Verify the RoryPlans MCP tools are reachable. If the tools are deferred, load them first: ToolSearch on the RoryPlans MCP for `get_next_task`, `complete_task`, and `fail_task`. If the server is not connected or returns 401/Unauthorized, stop and tell the user: the `RORYPLANS_MCP_TOKEN` environment variable is likely missing or expired — see the plugin README for token setup.
2. Determine the agent ID: use `$ARGUMENTS` if provided, otherwise `claude-code`.
3. Call `get_next_task` with `{ "agentId": "<agent id from step 2>" }`.
4. If no task is returned, report "no pending tasks for <agentId>" and stop. Do not invent work.
5. Execute the prompt returned by `get_next_task` in this environment (repo, tools, browser if available).
6. Verify the work actually succeeded (run tests, check output — whatever the task calls for).
7. On verified success: call `complete_task` with that `taskId`, the output, and a real summary of what was done.
8. If blocked or the work cannot be completed: call `fail_task` with that `taskId` and a clear reason.
9. Stop and report the outcome to the user. One task per cycle — do not pull another task.
