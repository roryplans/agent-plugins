---
name: setup
description: Configure the RoryPlans API token so the RoryPlans MCP server can authenticate. Use when the RoryPlans MCP server shows 401/Unauthorized, when RORYPLANS_MCP_TOKEN is missing, or when the user asks to set up or connect RoryPlans.
argument-hint: [token]
---

# Set up the RoryPlans token

Configure `RORYPLANS_MCP_TOKEN` so the RoryPlans MCP server (`https://www.roryplans.ai/api/mcp`) can authenticate.

1. Get the token:
   - If `$ARGUMENTS` contains a token, use it.
   - Otherwise ask the user to paste their RoryPlans API token. If they don't have one, tell them to create it first: sign in to RoryPlans → **Manage Agents → Connect Platform** (recommended — this also creates the agent ID that dispatch work is queued to), or the **API Tokens** page at https://www.roryplans.ai/api-tokens. An active RoryPlans subscription is required. Then wait for them to paste it.
2. Store it in `~/.claude/settings.json` under the `env` block, merging with any existing content — never overwrite other keys. Use a safe JSON merge, for example:

   ```bash
   python3 - "$HOME/.claude/settings.json" <<'EOF'
   import json, os, sys
   path = sys.argv[1]
   token = os.environ["NEW_RORYPLANS_TOKEN"]
   data = {}
   if os.path.exists(path):
       with open(path) as f:
           data = json.load(f)
   data.setdefault("env", {})["RORYPLANS_MCP_TOKEN"] = token
   with open(path, "w") as f:
       json.dump(data, f, indent=2)
       f.write("\n")
   EOF
   ```

   Pass the token via the `NEW_RORYPLANS_TOKEN` environment variable on the command (`NEW_RORYPLANS_TOKEN='<token>' python3 ...`) rather than interpolating it into the script body.
3. Never echo the token back in your response, and never write it anywhere other than the settings file. Note to the user that the pasted token is part of this chat transcript; if that concerns them, they can instead export `RORYPLANS_MCP_TOKEN` in their shell profile themselves and re-run this check.
4. Claude Code applies settings-file `env` entries to the process environment at startup, so the MCP connection authenticates from the **next** session. Tell the user: restart Claude Code (or start a new session), then verify with `claude mcp list` — the roryplans server should show Connected.
5. If it still shows 401 after restart, the token is invalid or expired — create a fresh one in RoryPlans and re-run `/roryplans:setup`.
