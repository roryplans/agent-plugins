"""RoryPlans plugin: add this session's token usage to complete_task / fail_task.

Claude Code runs this as a PreToolUse hook right before the RoryPlans
complete_task or fail_task tool call. It runs the plugin's own
scripts/usage-report.py (the same readable script the RoryPlans server
documents) on the session transcript Claude Code names in the hook input, and
adds the one-line JSON report it prints to the call as "usage".

- It reads only token counts, model names and timestamps, and sends nothing
  itself: the report travels inside the tool call the agent is already making.
- It never decides the call. It returns no permissionDecision, so permission
  rules, auto mode and prompts treat the call exactly as they would without
  the hook.
- It never blocks the call: on any problem it prints nothing and exits 0, and
  the call goes ahead unchanged.
"""

import json
import os
import re
import subprocess
import sys

SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "scripts",
    "usage-report.py",
)
TOOL = re.compile(r"^mcp__.+__(complete_task|fail_task)$")
TASK_ID = re.compile(r"^[A-Za-z0-9-]{1,64}$")
AGENT_ID = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
TIMEOUT_SECONDS = 12


def measure(task, transcript):
    env = dict(os.environ, RORYPLANS_USAGE_TRANSCRIPT=transcript)
    try:
        done = subprocess.run(
            [sys.executable, "-I", SCRIPT, task],
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=TIMEOUT_SECONDS,
            universal_newlines=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    lines = done.stdout.strip().splitlines()
    if not lines:
        return None
    try:
        report = json.loads(lines[-1])
    except ValueError:
        return None
    return report if isinstance(report, dict) else None


def transcripts(event):
    main = event.get("transcript_path")
    if not isinstance(main, str) or not main.endswith(".jsonl"):
        return []
    found = []
    # Inside a subagent the claim is usually in the subagent's own transcript.
    agent = event.get("agent_id")
    if isinstance(agent, str) and AGENT_ID.match(agent):
        sub = os.path.join(main[: -len(".jsonl")], "subagents", "agent-" + agent + ".jsonl")
        if os.path.isfile(sub):
            found.append(sub)
    found.append(main)
    return found


def updated_input(event):
    if event.get("hook_event_name") != "PreToolUse":
        return None
    name = event.get("tool_name")
    tool_input = event.get("tool_input")
    if not isinstance(name, str) or not TOOL.match(name) or not isinstance(tool_input, dict):
        return None
    task = tool_input.get("taskId")
    if not isinstance(task, str) or not TASK_ID.match(task):
        return None
    report = None
    for path in transcripts(event):
        report = measure(task, path)
        if not report or report.get("error") != "claim_not_found":
            break
    if not report:
        return None
    if not isinstance(report.get("models"), list):
        # A measurement error. Pass it on so RoryPlans records why there is
        # no usage, but never over a value the agent supplied itself.
        if "usage" in tool_input or not isinstance(report.get("error"), str):
            return None
    updated = dict(tool_input)
    updated["usage"] = report
    return updated


def main():
    try:
        event = json.load(sys.stdin)
    except ValueError:
        return
    if not isinstance(event, dict):
        return
    updated = updated_input(event)
    if updated is None:
        return
    sys.stdout.write(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "updatedInput": updated,
                }
            }
        )
    )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
