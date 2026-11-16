"""Run explicitly with Harbor installed; the simulator does not depend on Harbor."""

import asyncio
import hashlib
import json

import pytest

pytest.importorskip("harbor")

from harbor.models.agent.context import AgentContext  # noqa: E402
from harbor.models.task.task import Task  # noqa: E402

from backend.harbor import export_tasks  # noqa: E402
from backend.harbor_agent import PolicyAgent  # noqa: E402


def test_export_loads_in_real_harbor_task_model(tmp_path):
    root = export_tasks(tmp_path / "tasks", games=8, workers=2)
    task = Task(task_dir=root / "tcg-policy-0000")
    assert task.instruction
    assert task.config.verifier.environment_mode == "separate"
    assert task.config.verifier.timeout_sec >= 4 * 30


def test_actual_harbor_custom_agent_uploads_frozen_policy(tmp_path):
    policy = tmp_path / "policy.py"
    body = b"def select(observation, rng):\n    return []\n"
    policy.write_bytes(body)
    agent = PolicyAgent(logs_dir=tmp_path / "logs", policy_path=str(policy))
    policy.write_text("changed after trial initialization")
    uploads = []

    class Environment:
        async def upload_file(self, source_path, target_path):
            uploads.append((source_path.read_bytes(), target_path))

    environment = Environment()
    asyncio.run(agent.setup(environment))
    asyncio.run(agent.run("evaluate policy", environment, AgentContext()))
    assert uploads == [(body, "/app/policy.py")]
    receipt = json.loads((tmp_path / "logs/policy-manifest.json").read_text())
    assert receipt["sha256"] == hashlib.sha256(body).hexdigest()
