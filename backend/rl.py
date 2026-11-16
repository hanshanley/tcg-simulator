"""Bounded parallel policy evaluation with failure-inclusive win-rate rewards."""

import argparse
import hashlib
import json
import math
import os
import signal
import subprocess
import sys
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path

from backend.agents import agent_catalog
from backend.engine import engine_identity, starter_deck

ROOT = Path(__file__).resolve().parents[1]


def evaluation_config(
    *,
    games=128,
    workers=4,
    policy_seed=42,
    max_decisions=2000,
    timeout_seconds=30,
    opponents=None,
    decks=None,
    rollouts=False,
):
    for name, value in {
        "games": games,
        "workers": workers,
        "max_decisions": max_decisions,
    }.items():
        if type(value) is not int or value < 1:
            raise ValueError(f"{name} must be a positive integer.")
    if type(policy_seed) is not int:
        raise ValueError("policy_seed must be an integer.")
    if (
        isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, (int, float))
        or not math.isfinite(timeout_seconds)
        or timeout_seconds <= 0
    ):
        raise ValueError("timeout_seconds must be finite and positive.")
    opponents = ["random", "first"] if opponents is None else opponents
    if (
        not isinstance(opponents, list)
        or not opponents
        or any(opponent not in ("random", "first") for opponent in opponents)
    ):
        raise ValueError("Supply a nonempty opponent list containing 'random' and/or 'first'.")
    decks = [starter_deck(), starter_deck()] if decks is None else decks
    from backend.rl_env import CABTEnv

    validated = CABTEnv(decks=decks, max_decisions=max_decisions)
    if type(rollouts) is not bool:
        raise ValueError("rollouts must be boolean.")
    return {
        "games": games,
        "workers": min(workers, games),
        "policy_seed": policy_seed,
        "max_decisions": max_decisions,
        "timeout_seconds": timeout_seconds,
        "opponents": list(opponents),
        "decks": validated.decks,
        "rollouts": rollouts,
    }


def game_config(config, index):
    return {
        "decks": config["decks"],
        "opponent": config["opponents"][(index // 2) % len(config["opponents"])],
        "reverse": bool(index % 2),
        "policy_seed": config["policy_seed"] + index * 2,
        "max_decisions": config["max_decisions"],
        "rollouts": config["rollouts"],
    }


def reward_summary(games):
    counts = {key: 0 for key in ("wins", "losses", "draws", "failed", "capped")}
    for game in games:
        status, winner = game["status"], game.get("winner")
        if status == "completed":
            counts[{0: "wins", 1: "losses", None: "draws"}[winner]] += 1
        elif status in ("failed", "capped"):
            counts[status] += 1
        else:
            raise ValueError(f"Unknown game status: {status}")
    total = sum(counts.values())
    completed = counts["wins"] + counts["losses"] + counts["draws"]
    rate = counts["wins"] / total if total else 0.0
    if total:
        z2 = 1.959963984540054**2
        center = (rate + z2 / (2 * total)) / (1 + z2 / total)
        half = (
            math.sqrt(rate * (1 - rate) / total + z2 / (4 * total**2))
            * math.sqrt(z2)
            / (1 + z2 / total)
        )
        interval = [max(0.0, center - half), min(1.0, center + half)]
    else:
        interval = None
    return {
        **counts,
        "scheduled_games": total,
        "completed": completed,
        "reward": rate,
        "win_rate": rate,
        "win_percentage": rate * 100,
        "win_rate_ci95": interval,
        "completed_game_win_rate": counts["wins"] / completed if completed else None,
        "completion_rate": completed / total if total else 0.0,
        "reward_definition": (
            "candidate wins / all scheduled games; draws, caps and failures earn 0"
        ),
    }


def _match(config, policy, output, timeout):
    output.mkdir()
    config_path = output / "config.json"
    config_path.write_text(json.dumps(config) + "\n")
    started = time.monotonic()
    try:
        with (output / "worker.log").open("w") as log:
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "backend.rl_worker",
                    str(config_path),
                    policy,
                    str(output),
                ],
                cwd=ROOT,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            try:
                process.wait(timeout=timeout)
            finally:
                # Reap policy-spawned children too; process isolation is not a sandbox.
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
        if process.returncode:
            raise RuntimeError(f"Worker exited with code {process.returncode}; see worker.log.")
        result = json.loads((output / "result.json").read_text())
        if not isinstance(result, dict) or result.get("status") not in (
            "completed",
            "capped",
            "failed",
        ):
            raise ValueError("Worker returned an invalid result status.")
        if "winner" not in result:
            raise ValueError("Worker result has no winner field.")
        winner = result["winner"]
        if winner is not None and (type(winner) is not int or winner not in (0, 1)):
            raise ValueError("Worker returned an invalid winner.")
        if result["status"] != "completed" and winner is not None:
            raise ValueError("Unfinished games cannot have a winner.")
    except (subprocess.TimeoutExpired, OSError, ValueError, RuntimeError) as error:
        result = {
            "status": "failed",
            "winner": None,
            "reward": 0.0,
            "decisions": 0,
            "duration_ms": round((time.monotonic() - started) * 1000, 2),
            "error": (
                f"Match exceeded {timeout}s wall-clock limit."
                if isinstance(error, subprocess.TimeoutExpired)
                else str(error)
            ),
        }
    return result


def evaluate(policy, output, **settings):
    config = evaluation_config(**settings)
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    if policy in ("random", "first"):
        identity = next(agent for agent in agent_catalog() if agent["id"] == policy)
    else:
        source = Path(policy).resolve()
        body = source.read_bytes()
        frozen = output / "policy.py"
        frozen.write_bytes(body)
        identity = {"name": source.name, "artifact_sha256": hashlib.sha256(body).hexdigest()}
        policy = str(frozen)
    engine = engine_identity()
    manifest = {
        "schema": "tcg-policy-evaluation-v1",
        "config": config,
        "policy": identity,
        "engine": engine,
        "python_version": sys.version,
        "native_rng_seeded": False,
        "runtime_sha256": {
            name: hashlib.sha256((Path(__file__).parent / name).read_bytes()).hexdigest()
            for name in (
                "rl.py",
                "rl_env.py",
                "rl_worker.py",
                "agents.py",
                "engine.py",
                "harbor.py",
            )
        },
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    started = time.monotonic()
    game_root = output / "games"
    game_root.mkdir()

    def run(index):
        protocol = game_config(config, index)
        result = _match(protocol, policy, game_root / f"{index:07d}", config["timeout_seconds"])
        result.update(game=index, protocol=protocol)
        result["reward"] = float(result["status"] == "completed" and result["winner"] == 0)
        (game_root / f"{index:07d}" / "result.json").write_text(json.dumps(result) + "\n")
        return result

    def results(executor, stream):
        indices = iter(range(config["games"]))
        pending = {
            executor.submit(run, index) for index in range(min(config["workers"], config["games"]))
        }
        for _ in range(len(pending)):
            next(indices)
        while pending:
            finished, pending = wait(pending, return_when=FIRST_COMPLETED)
            for future in finished:
                result = future.result()
                stream.write(json.dumps(result) + "\n")
                stream.flush()
                yield result
                index = next(indices, None)
                if index is not None:
                    pending.add(executor.submit(run, index))

    with ThreadPoolExecutor(max_workers=config["workers"]) as executor:
        with (output / "games.jsonl").open("w") as stream:
            summary = reward_summary(results(executor, stream))
    summary["duration_seconds"] = round(time.monotonic() - started, 3)
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def add_evaluation_arguments(parser):
    parser.add_argument("--games", type=int, default=128)
    parser.add_argument("--workers", type=int, default=min(4, os.cpu_count() or 1))
    parser.add_argument("--policy-seed", type=int, default=42)
    parser.add_argument("--max-decisions", type=int, default=2000)
    parser.add_argument("--timeout-seconds", type=float, default=30)
    parser.add_argument("--opponents", nargs="+", choices=("random", "first"), default=None)
    parser.add_argument("--decks", type=Path, help="JSON with two 60-card CABT ID lists.")
    parser.add_argument("--rollouts", action="store_true", help="Save candidate-only transitions.")


def settings_from_args(args):
    return {
        key: json.loads(value.read_text()) if key == "decks" and value else value
        for key in (
            "games",
            "workers",
            "policy_seed",
            "max_decisions",
            "timeout_seconds",
            "opponents",
            "decks",
            "rollouts",
        )
        if (value := getattr(args, key)) is not None
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", default="random", help="random, first, or a .py file.")
    parser.add_argument("--output", type=Path, required=True, help="New evaluation directory.")
    add_evaluation_arguments(parser)
    args = parser.parse_args()
    try:
        summary = evaluate(args.policy, args.output, **settings_from_args(args))
    except (ValueError, OSError) as error:
        parser.exit(2, f"{error}\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
