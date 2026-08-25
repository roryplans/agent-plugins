---
name: roryplans-tasks
description: How to work with RoryPlans over MCP — plan management tools and the agent dispatch task queue. Use when the user mentions RoryPlans, RoryPlans plans or tasks, the RoryPlans task queue, or asks to pull/complete/fail dispatched agent work.
---

# RoryPlans tasks and plans over MCP

RoryPlans is a planning platform. This plugin connects Claude Code to the RoryPlans remote MCP server (`https://www.roryplans.ai/api/mcp`), which exposes two tool families:

## Plan tools

- `create_plan` — create a new plan from a natural-language prompt.
- `modify_plan` — add goals or tasks, update fields, reschedule, or delete items in a plan.
- `duplicate_plan` — copy an existing plan with optional overrides (name, description, budget, dates, themes).
- `list_plans` — list plans the user owns or that are shared with their team.
- `list_tasks` — list the strategic themes, goals, and tasks inside a plan.

## Agent dispatch tools (task queue)

RoryPlans can dispatch queued work to coding agents. These tools implement a pull model:

- `get_next_task` — claim the next pending dispatch task for an agent ID and receive its composed prompt.
- `list_pending_tasks` — list pending and claimed dispatch tasks for an agent ID.
- `complete_task` — mark a task completed with a summary and optional agent output.
- `fail_task` — mark a task failed with an error message.

## Task-loop contract

Follow this contract exactly when pulling dispatched work:

1. Pull ONE task with `get_next_task` using `{ "agentId": "claude-code" }`. Use a different literal only if the user created a custom platform agent or extra bridge in RoryPlans Manage Agents (accepted values: `claude_cowork`, `claude-code`, `codex`, a Custom Platform agent id, or a bridge agent config UUID).
2. Execute the prompt returned by `get_next_task` in this environment (repo, tools, browser if available).
3. Verify the work actually succeeded.
4. Call `complete_task` with that `taskId`, the output, and a real summary of what was done — ONLY after the work is verified. Never mark unverified or fabricated work complete.
5. If blocked or the task cannot be done, call `fail_task` with that `taskId` and a clear reason instead.
6. One task per cycle. After completing or failing a task, stop and report — do not pull another unless asked.
7. If the queue is empty, report "no pending tasks" and stop. Never invent work.

## Failure modes

- **401 / Unauthorized**: the `RORYPLANS_MCP_TOKEN` environment variable is missing, empty, or expired. Tell the user to follow the token setup steps in the plugin README (create a token in RoryPlans, export it in their shell profile, restart Claude Code).
- **Empty queue**: `get_next_task` returns no task. Report "no pending tasks" — do not fabricate work.
- **No tasks for this agent ID**: dispatch tools only return work queued for the matching `agentId`. Ask the user to check the agent ID in RoryPlans Manage Agents and confirm work was dispatched.
