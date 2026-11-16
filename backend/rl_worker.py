"""One policy, one native game, one process. Invoked by backend.rl."""

import argparse
import copy
import importlib.util
import json
import random
import time
from pathlib import Path

from backend.agents import choose
from backend.rl_env import CABTEnv


def load_policy(spec):
    if spec in ("random", "first"):
        return lambda observation, rng: choose(spec, observation, rng)[0]
    path = Path(spec)
    module_spec = importlib.util.spec_from_file_location("_tcg_policy", path)
    if module_spec is None or module_spec.loader is None:
        raise ValueError("Policy must be 'random', 'first', or a Python file.")
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    if not callable(getattr(module, "select", None)):
        raise ValueError("Policy must define select(observation, rng).")
    return module.select


def play(config, policy, output):
    started = time.monotonic()
    result = {"status": "failed", "winner": None, "decisions": 0}
    try:
        select = load_policy(policy)
        rng = random.Random(config["policy_seed"])
        with CABTEnv(
            decks=config["decks"],
            opponent=config["opponent"],
            max_decisions=config["max_decisions"],
            reverse=config["reverse"],
        ) as env:
            observation, info = env.reset(seed=config["policy_seed"])
            result.update(info)
            result["engine"] = env.engine
            terminated = info["status"] == "completed"
            truncated = info["status"] == "capped"
            trace = output / "rollout.jsonl"
            with trace.open("w") as stream:
                while not (terminated or truncated):
                    before = copy.deepcopy(observation) if config["rollouts"] else None
                    policy_started = time.perf_counter()
                    action = select(observation, rng)
                    latency_ms = (time.perf_counter() - policy_started) * 1000
                    observation, reward, terminated, truncated, info = env.step(action)
                    result.update(info)
                    if config["rollouts"]:
                        stream.write(
                            json.dumps(
                                {
                                    "observation": before,
                                    "action": action,
                                    "latency_ms": round(latency_ms, 4),
                                    "next_observation": observation,
                                    "reward": reward,
                                    "terminated": terminated,
                                    "truncated": truncated,
                                }
                            )
                            + "\n"
                        )
                result.update(info)
    except Exception as error:
        result.update(status="failed", winner=None, error=f"{type(error).__name__}: {error}")
    result["reward"] = float(result["status"] == "completed" and result["winner"] == 0)
    result["duration_ms"] = round((time.monotonic() - started) * 1000, 2)
    (output / "result.json").write_text(json.dumps(result) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("config", type=Path)
    parser.add_argument("policy")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    play(json.loads(args.config.read_text()), args.policy, args.output)


if __name__ == "__main__":
    main()
