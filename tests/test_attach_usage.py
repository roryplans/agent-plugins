"""Tests for the Claude Code usage hook (plugin/hooks/attach-usage.py).

Run from the repo root:  python3 -m unittest discover -s tests
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(ROOT, "plugin", "hooks", "attach-usage.py")
SCRIPT = os.path.join(ROOT, "plugin", "scripts", "usage-report.py")

# Pinned on both sides: roryplans lib/agents/external-usage/__tests__/usage-script.test.ts
SCRIPT_SHA256 = "e11046d320056c2dbd0be499704a3d82bc92e3d50d4f4c44a68e667261daf5e4"

TASK = "11111111-2222-4333-8444-555555555555"
SID = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
TOOL = "mcp__plugin_roryplans_roryplans__complete_task"


def claim(task, ts, tool_use_id="tu_claim"):
    return [
        {
            "type": "assistant",
            "timestamp": "2026-10-06T10:00:00.500Z",
            "message": {
                "id": "msg_claim_" + tool_use_id,
                "model": "claude-opus-5-5",
                "content": [
                    {
                        "type": "tool_use",
                        "id": tool_use_id,
                        "name": "mcp__plugin_roryplans_roryplans__get_next_task",
                        "input": {"agentId": "claude-code"},
                    }
                ],
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        },
        {
            "type": "user",
            "timestamp": ts,
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(
                                    {
                                        "taskId": task,
                                        "prompt": "do it",
                                        "usageReporting": {
                                            "version": 3,
                                            "delivery": "plugin_hook",
                                        },
                                    }
                                ),
                            }
                        ],
                    }
                ],
            },
        },
    ]


def assistant(message_id, ts, input_tokens, output_tokens):
    return {
        "type": "assistant",
        "timestamp": ts,
        "message": {
            "id": message_id,
            "model": "claude-opus-5-5",
            "content": [{"type": "text", "text": "hi"}],
            "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
        },
    }


class AttachUsageHookTest(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="rory-hook-")
        self.transcript = os.path.join(self.home, ".claude", "projects", "-repo", SID + ".jsonl")

    def tearDown(self):
        shutil.rmtree(self.home, ignore_errors=True)

    def write(self, path, records):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            for record in records:
                fh.write(json.dumps(record) + "\n")

    def event(self, **overrides):
        event = {
            "session_id": SID,
            "transcript_path": self.transcript,
            "cwd": self.home,
            "permission_mode": "auto",
            "hook_event_name": "PreToolUse",
            "tool_name": TOOL,
            "tool_input": {"taskId": TASK, "summary": "done"},
            "tool_use_id": "tu_complete",
        }
        event.update(overrides)
        return event

    def run_hook(self, stdin):
        done = subprocess.run(
            [sys.executable, HOOK],
            input=stdin if isinstance(stdin, str) else json.dumps(stdin),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={"PATH": os.environ.get("PATH", ""), "HOME": self.home},
            universal_newlines=True,
            timeout=60,
        )
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout) if done.stdout.strip() else None

    def test_vendored_script_is_the_pinned_copy(self):
        with open(SCRIPT, "rb") as fh:
            self.assertEqual(hashlib.sha256(fh.read()).hexdigest(), SCRIPT_SHA256)

    def test_adds_measured_usage_without_deciding_the_call(self):
        self.write(
            self.transcript,
            claim(TASK, "2026-10-06T10:00:01.000Z")
            + [assistant("msg_1", "2026-10-06T10:00:05.000Z", 4, 6)],
        )
        out = self.run_hook(self.event())
        specific = out["hookSpecificOutput"]
        self.assertEqual(specific["hookEventName"], "PreToolUse")
        # No permission decision: rules, auto mode and prompts still apply.
        self.assertNotIn("permissionDecision", specific)
        self.assertEqual(set(out), {"hookSpecificOutput"})
        updated = specific["updatedInput"]
        self.assertEqual(updated["taskId"], TASK)
        self.assertEqual(updated["summary"], "done")
        self.assertEqual(updated["usage"]["agent"], "claude-code")
        self.assertEqual(updated["usage"]["taskId"], TASK)
        self.assertEqual(
            [(m["model"], m["inputTokens"], m["outputTokens"]) for m in updated["usage"]["models"]],
            [("claude-opus-5-5", 4, 6)],
        )

    def test_measured_usage_replaces_a_value_the_agent_passed(self):
        self.write(
            self.transcript,
            claim(TASK, "2026-10-06T10:00:01.000Z")
            + [assistant("msg_1", "2026-10-06T10:00:05.000Z", 4, 6)],
        )
        event = self.event(tool_input={"taskId": TASK, "error": "blocked", "usage": {"models": "guess"}})
        event["tool_name"] = "mcp__plugin_roryplans_roryplans__fail_task"
        updated = self.run_hook(event)["hookSpecificOutput"]["updatedInput"]
        self.assertEqual(updated["error"], "blocked")
        self.assertIsInstance(updated["usage"]["models"], list)

    def test_passes_a_measurement_error_on_but_never_over_the_agents_value(self):
        self.write(self.transcript, [assistant("msg_1", "2026-10-06T10:00:05.000Z", 4, 6)])
        updated = self.run_hook(self.event())["hookSpecificOutput"]["updatedInput"]
        self.assertEqual(updated["usage"], {"v": 1, "error": "claim_not_found"})
        own = {"v": 1, "source": "transcript", "models": []}
        self.assertIsNone(self.run_hook(self.event(tool_input={"taskId": TASK, "usage": own})))

    def test_prefers_the_subagent_transcript_then_the_main_one(self):
        subagent = os.path.join(self.home, ".claude", "projects", "-repo", SID, "subagents", "agent-abc.jsonl")
        self.write(self.transcript, [assistant("msg_main", "2026-10-06T10:00:30.000Z", 900, 900)])
        self.write(
            subagent,
            claim(TASK, "2026-10-06T10:00:01.000Z")
            + [assistant("msg_sub", "2026-10-06T10:00:05.000Z", 3, 5)],
        )
        usage = self.run_hook(self.event(agent_id="abc"))["hookSpecificOutput"]["updatedInput"]["usage"]
        self.assertEqual([(m["inputTokens"], m["outputTokens"]) for m in usage["models"]], [(3, 5)])

        # Claimed in the main session, completed from a subagent: falls back.
        self.write(subagent, [assistant("msg_sub", "2026-10-06T10:00:05.000Z", 3, 5)])
        self.write(
            self.transcript,
            claim(TASK, "2026-10-06T10:00:01.000Z")
            + [assistant("msg_main", "2026-10-06T10:00:30.000Z", 7, 8)],
        )
        usage = self.run_hook(self.event(agent_id="abc"))["hookSpecificOutput"]["updatedInput"]["usage"]
        self.assertEqual(usage["agent"], "claude-code")
        # The main session counts its subagents too.
        self.assertEqual(sum(m["inputTokens"] for m in usage["models"]), 7 + 3)

    def test_leaves_other_calls_alone(self):
        self.write(
            self.transcript,
            claim(TASK, "2026-10-06T10:00:01.000Z")
            + [assistant("msg_1", "2026-10-06T10:00:05.000Z", 4, 6)],
        )
        for event in [
            self.event(tool_name="mcp__plugin_roryplans_roryplans__get_next_task"),
            self.event(tool_name="Bash", tool_input={"command": "ls", "taskId": TASK}),
            self.event(hook_event_name="PostToolUse"),
            self.event(tool_input={"taskId": "x'; rm -rf ~", "summary": "done"}),
            self.event(tool_input={"summary": "no task"}),
            self.event(transcript_path=os.path.join(self.home, "notes.txt")),
            self.event(transcript_path=None),
        ]:
            self.assertIsNone(self.run_hook(event), event)

    def test_never_fails_the_call(self):
        for stdin in ["", "not json", "[]", json.dumps({"tool_input": 5})]:
            self.assertIsNone(self.run_hook(stdin))


if __name__ == "__main__":
    unittest.main()
