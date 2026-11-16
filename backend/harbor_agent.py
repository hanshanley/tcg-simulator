"""Harbor custom agent for evaluating an existing, self-contained policy artifact."""

import hashlib
import json
from pathlib import Path

from harbor.agents.base import BaseAgent
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext


class PolicyAgent(BaseAgent):
    @staticmethod
    def name() -> str:
        return "counterplay-policy"

    def version(self) -> str:
        return "1.0.0"

    def __init__(self, logs_dir: Path, model_name=None, *, policy_path: str, **kwargs):
        super().__init__(logs_dir=logs_dir, model_name=model_name, **kwargs)
        self.policy_path = Path(policy_path).expanduser().resolve()
        if not self.policy_path.is_file():
            raise ValueError("policy_path must name a self-contained Python policy file.")
        self.policy_bytes = self.policy_path.read_bytes()

    async def setup(self, environment: BaseEnvironment) -> None:
        pass

    async def run(
        self, instruction: str, environment: BaseEnvironment, context: AgentContext
    ) -> None:
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        frozen = self.logs_dir / "policy.py"
        frozen.write_bytes(self.policy_bytes)
        await environment.upload_file(source_path=frozen, target_path="/app/policy.py")
        (self.logs_dir / "policy-manifest.json").write_text(
            json.dumps(
                {
                    "policy": self.policy_path.name,
                    "sha256": hashlib.sha256(self.policy_bytes).hexdigest(),
                    "evaluation": "Harbor verifier; no model API call",
                },
                indent=2,
            )
            + "\n"
        )
