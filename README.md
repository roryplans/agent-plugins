# RoryPlans plugin for Claude Code

Connect Claude Code to [RoryPlans](https://www.roryplans.ai): plan management tools and the coding-agent dispatch queue, delivered over the RoryPlans remote MCP server.

Installing this plugin gives you:

- **The RoryPlans MCP server**, auto-configured (`https://www.roryplans.ai/api/mcp`) — plan tools (`create_plan`, `modify_plan`, `duplicate_plan`, `list_plans`, `list_tasks`) and dispatch-queue tools (`get_next_task`, `list_pending_tasks`, `complete_task`, `fail_task`).
- **`/roryplans:setup`** — guided token setup (stores `RORYPLANS_MCP_TOKEN` in your Claude Code settings).
- **`/roryplans:next`** — pull and execute the next queued dispatch task, then report back. One task per cycle.
- **`/roryplans:tasks`** — list pending dispatch tasks for your agent.
- **A task-loop skill** Claude uses automatically whenever you talk about RoryPlans plans or queued agent work.

## Install

```bash
claude plugin marketplace add roryplans/claude-plugin
claude plugin install roryplans@roryplans
```

## Token setup (required)

The MCP server authenticates with a RoryPlans API token read from the `RORYPLANS_MCP_TOKEN` environment variable.

**Easiest path:** start a `claude` session and run `/roryplans:setup`. It walks you through creating a token, stores it in `~/.claude/settings.json` (`env` block), and tells you how to verify. Then restart Claude Code. (Note: a token pasted into chat becomes part of that conversation's transcript — use the manual path below if you'd rather keep it out.)

**Manual path:**

1. Sign in to RoryPlans and create a token:
   - **Manage Agents → Connect Platform** (recommended for the dispatch queue — this also creates the agent ID work is dispatched to), or
   - the **[API Tokens](https://www.roryplans.ai/api-tokens)** page.

   An active RoryPlans subscription is required to create tokens.
2. Export it in your shell profile (`~/.zshrc`, `~/.bashrc`, …):

   ```bash
   export RORYPLANS_MCP_TOKEN=rp_your_token_here
   ```

3. Restart your shell (or `source` the profile) and start a new `claude` session.
4. Verify: `claude mcp list` should show **roryplans** as connected.

> **Important:** if `RORYPLANS_MCP_TOKEN` is not set, the `${RORYPLANS_MCP_TOKEN}` placeholder in the plugin's MCP config is **not** expanded — the literal string is sent as the bearer token, every call fails with 401, and `claude mcp list` shows a warning about the unset variable. Export the variable in the environment Claude Code starts from, then start a new session.

## Usage

Pull and run the next queued task (defaults to agent ID `claude-code`):

```
/roryplans:next
```

With a custom agent ID (from Manage Agents — a Custom Platform id or bridge config UUID):

```
/roryplans:next my-custom-agent-id
```

List pending tasks without claiming anything:

```
/roryplans:tasks
```

Plan tools work through normal conversation, e.g. *"Create a RoryPlans plan for launching our customer onboarding campaign next month"* or *"List my RoryPlans plans."*

## Troubleshooting

**`claude mcp list` shows roryplans as failed, or every call returns 401 / Unauthorized**
`RORYPLANS_MCP_TOKEN` is missing, empty, or expired in the environment Claude Code was started from. Re-check the token setup steps above, then start a new session. If the token was revoked, create a new one in RoryPlans.

**No plans found**
Confirm the token belongs to the RoryPlans user you expect, and that the plan is owned by that user or shared with their team.

**`/roryplans:next` or `/roryplans:tasks` reports no pending tasks**
Dispatch tools only return work queued for the matching agent ID. Check the agent ID in RoryPlans **Manage Agents** and make sure work has actually been dispatched to it. If you connected via a Custom Platform or extra bridge, pass its id explicitly: `/roryplans:next <agentId>`.

**Token creation blocked**
Creating API tokens or OAuth clients requires an active RoryPlans subscription.

## More

Full connector documentation (including OAuth setup for the Claude apps): https://www.roryplans.ai/documentation/claude-connector
