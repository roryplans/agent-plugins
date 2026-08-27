# RoryPlans agent plugins

Connect your coding agent — **Claude Code** or **Codex** — to [RoryPlans](https://www.roryplans.ai): plan management tools and the coding-agent dispatch queue, delivered over the RoryPlans remote MCP server. One repo, one plugin, dual manifests.

Installing the plugin gives you:

- **The RoryPlans MCP server**, auto-configured (`https://www.roryplans.ai/api/mcp`) — plan tools (`create_plan`, `modify_plan`, `duplicate_plan`, `list_plans`, `list_tasks`) and dispatch-queue tools (`get_next_task`, `list_pending_tasks`, `complete_task`, `fail_task`).
- **`setup`** — guided token setup (`/roryplans:setup` in Claude Code).
- **`next`** — pull and execute the next queued dispatch task, then report back. One task per cycle. (`/roryplans:next` in Claude Code.)
- **`tasks`** — list pending dispatch tasks for your agent. (`/roryplans:tasks` in Claude Code.)
- **A task-loop skill** the agent uses automatically whenever you talk about RoryPlans plans or queued agent work.

> This repo was previously named `roryplans/claude-plugin`; GitHub redirects keep existing installs working.

## Install — Claude Code

```bash
claude plugin marketplace add roryplans/agent-plugins
claude plugin install roryplans@roryplans
```

## Install — Codex

```bash
codex plugin marketplace add roryplans/agent-plugins
codex plugin add roryplans
```

The plugin ships a `SessionStart` hook that adds a short reminder to the session context when `RORYPLANS_MCP_TOKEN` is not set (context only — it runs no side effects). Codex's hook trust model marks newly installed or changed plugin hooks for review and skips them until you trust them: run `/hooks` inside a Codex session to review and trust the hook.

If you'd rather skip the plugin and only connect the MCP server:

```bash
codex mcp add roryplans --url https://www.roryplans.ai/api/mcp --bearer-token-env-var RORYPLANS_MCP_TOKEN
```

## Token setup (required)

The MCP server authenticates with a RoryPlans API token read from the `RORYPLANS_MCP_TOKEN` environment variable.

**Easiest path:** start a session and run the setup command — `/roryplans:setup` in Claude Code, or ask Codex to run the plugin's `setup` skill. It walks you through creating a token, stores it (Claude Code: `~/.claude/settings.json` `env` block; Codex: your shell profile), and tells you how to verify. Then restart. (Note: a token pasted into chat becomes part of that conversation's transcript — use the manual path below if you'd rather keep it out.)

**Manual path:**

1. Sign in to RoryPlans and create a token:
   - **Manage Agents → Connect Platform** (recommended for the dispatch queue — this also creates the agent ID work is dispatched to), or
   - the **[API Tokens](https://www.roryplans.ai/api-tokens)** page.

   An active RoryPlans subscription is required to create tokens.
2. Export it in your shell profile (`~/.zshrc`, `~/.bashrc`, …):

   ```bash
   export RORYPLANS_MCP_TOKEN=rp_your_token_here
   ```

3. Restart your shell (or `source` the profile) and start a new `claude` / `codex` session.
4. Verify: `claude mcp list` should show **roryplans** as connected; in Codex, run `/mcp`.

> **Important (Claude Code):** if `RORYPLANS_MCP_TOKEN` is not set, the `${RORYPLANS_MCP_TOKEN}` placeholder in the plugin's MCP config is **not** expanded — the literal string is sent as the bearer token, every call fails with 401, and `claude mcp list` shows a warning about the unset variable. Export the variable in the environment Claude Code starts from, then start a new session. Codex reads the variable by name (`bearer_token_env_var`) and simply fails auth until it's set.

## Usage

Pull and run the next queued task (defaults to agent ID `claude-code` on Claude Code, `codex` on Codex):

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

In Codex, invoke the same skills from the `$`/`/skills` menu (`next`, `tasks`, `setup`), or just ask for them by name.

Plan tools work through normal conversation, e.g. *"Create a RoryPlans plan for launching our customer onboarding campaign next month"* or *"List my RoryPlans plans."*

## Troubleshooting

**MCP server shows failed / every call returns 401 Unauthorized**
`RORYPLANS_MCP_TOKEN` is missing, empty, or expired in the environment the app was started from. Re-check the token setup steps above, then start a new session. If the token was revoked, create a new one in RoryPlans.

**No plans found**
Confirm the token belongs to the RoryPlans user you expect, and that the plan is owned by that user or shared with their team.

**`next` / `tasks` reports no pending tasks**
Dispatch tools only return work queued for the matching agent ID. Check the agent ID in RoryPlans **Manage Agents** and make sure work has actually been dispatched to it. If you connected via a Custom Platform or extra bridge, pass its id explicitly, e.g. `/roryplans:next <agentId>`.

**Token creation blocked**
Creating API tokens or OAuth clients requires an active RoryPlans subscription.

## More

Full connector documentation (including OAuth setup for the Claude apps): https://www.roryplans.ai/documentation/claude-connector
