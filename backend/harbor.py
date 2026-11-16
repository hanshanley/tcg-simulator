"""Export standalone Harbor tasks, or execute their policy win-rate verifier."""

import argparse
import json
import math
import shutil
import tempfile
from pathlib import Path

from backend.engine import ENGINE_VERSION
from backend.rl import (
    RUNTIME_FILES,
    add_evaluation_arguments,
    evaluate,
    evaluation_config,
    settings_from_args,
)

ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = f"""FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends libstdc++6 libgomp1 \\
    && apt-get clean
RUN pip install --no-cache-dir --no-deps kaggle-environments=={ENGINE_VERSION}
COPY runtime /opt/tcg
ENV PYTHONPATH=/opt/tcg
WORKDIR /app
RUN python -c "from backend.engine import engine_identity; print(engine_identity())"
"""

VERIFY_SCRIPT = """#!/bin/bash
set -euo pipefail
tests_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="$tests_dir/runtime"
exec python -m backend.harbor verify \\
  --config "$tests_dir/evaluation.json" \\
  --policy "${1:-/app/policy.py}" \\
  --output "${2:-/logs/verifier}"
"""

EXAMPLE_POLICY = '''"""Replace this baseline with a trained policy; return legal option indices."""


def select(observation, rng):
    selection = observation["select"]
    maximum = min(selection["maxCount"], len(selection["option"]))
    count = rng.randint(selection["minCount"], maximum)
    return rng.sample(range(len(selection["option"])), count)
'''

INSTRUCTION = """# CABT policy win-rate environment

Write a self-contained Python policy to `/app/policy.py` defining:

```python
def select(observation: dict, rng) -> list[int]:
    ...
```

`observation` is CABT's observation for candidate player 0, not privileged engine
state. `observation["select"]` contains `option`, `minCount` and `maxCount`.
Return distinct, zero-based indices into `option`, satisfying those bounds.
For optional choices, an empty list is legal only when `minCount` is zero.
Use the supplied `random.Random` instance for policy randomness.
Keep episode-local memory in your module; it is reloaded in a fresh process for
each game. Do not retain a previous game's observations.

The verifier evaluates {games} independent games against {opponents}, with at
most {workers} workers, {max_decisions} native selections per game (both players
combined), and {timeout_seconds} seconds per game, including policy loading.
Candidate always remains player 0. Games alternate who chooses first/second;
this is not a guarantee of who takes the first turn.

**Reward = candidate wins / all {games} scheduled games**, in [0, 1].
Draws, capped games, invalid actions, policy errors, crashes and timeouts earn
zero and remain in the denominator. The completed-game win rate is diagnostic
only. CABT's native shuffles and coin flips cannot be seeded; policy seeds do not
make native matches exactly reproducible.

Use `/app/example_policy.py` as a starting point. The simulator is importable as
`backend.rl_env.CABTEnv`. For local practice inside the environment:

```sh
python -m backend.rl --policy /app/policy.py --games 16 --workers 2 --output /app/practice
```

The task is the pinned CABT rules/card pool, NOT current tournament Standard.
No external service, model API, or Kaggle submission is required. Python policies
must use the installed runtime (standard library by default); extend the image
before adding ML dependencies. Only `/app/policy.py` transfers to verification.
Evaluation traces are research artifacts, never inputs to an active opponent.
"""


def export_tasks(output, *, tasks=1, **settings):
    config = evaluation_config(**settings)
    if type(tasks) is not int or tasks < 1:
        raise ValueError("tasks must be a positive integer.")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    for index in range(tasks):
        task = output / f"tcg-policy-{index:04d}"
        task_config = {**config, "policy_seed": config["policy_seed"] + index * config["games"] * 2}
        for directory in ("environment", "tests"):
            runtime = task / directory / "runtime/backend"
            runtime.mkdir(parents=True)
            for name in RUNTIME_FILES:
                shutil.copyfile(ROOT / "backend" / name, runtime / name)
        (task / "environment/Dockerfile").write_text(DOCKERFILE)
        (task / "environment/example_policy.py").write_text(EXAMPLE_POLICY)
        with (task / "environment/Dockerfile").open("a") as stream:
            stream.write("COPY example_policy.py /app/example_policy.py\n")
        (task / "instruction.md").write_text(
            INSTRUCTION.format(**{**config, "opponents": ", ".join(config["opponents"])})
        )
        timeout = (
            math.ceil(config["games"] / config["workers"]) * (config["timeout_seconds"] + 2) + 120
        )
        (task / "task.toml").write_text(
            'schema_version = "1.4"\n'
            'artifacts = ["/app/policy.py"]\n\n'
            "[task]\n"
            f'name = "counterplay/tcg-policy-{index:04d}"\n'
            'version = "1.0.0"\n'
            'description = "CABT policy evaluation with failure-inclusive win-rate reward"\n\n'
            "[metadata]\n"
            'category = "reinforcement-learning"\n'
            'reward = "wins / scheduled games"\n'
            f'engine_package = "kaggle-environments=={ENGINE_VERSION}"\n'
            "native_rng_seeded = false\n\n"
            "[agent]\n"
            "timeout_sec = 600.0\n\n"
            "[verifier]\n"
            'environment_mode = "separate"\n'
            f"timeout_sec = {float(timeout)}\n\n"
            "[environment]\n"
            f"cpus = {config['workers']}\n"
            f"memory_mb = {max(2048, config['workers'] * 512)}\n"
            "storage_mb = 10240\n"
            'workdir = "/app"\n'
        )
        (task / "tests/evaluation.json").write_text(json.dumps(task_config, indent=2) + "\n")
        script = task / "tests/test.sh"
        script.write_text(VERIFY_SCRIPT)
        script.chmod(0o755)
        solution = task / "solution"
        solution.mkdir()
        solve = solution / "solve.sh"
        solve.write_text(
            "#!/bin/bash\nset -euo pipefail\ncp /app/example_policy.py /app/policy.py\n"
        )
        solve.chmod(0o755)
    return output


def write_reward(output, value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Reward must be a finite number in [0, 1].")
    if not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError("Reward must be a finite number in [0, 1].")
    # Harbor prefers JSON over text; replace any previous canonical score first.
    temporary = output / "reward.json.tmp"
    temporary.write_text(json.dumps({"reward": value}) + "\n")
    temporary.replace(output / "reward.json")
    (output / "reward.txt").write_text(f"{value:.17g}\n")


def verify(config_path, policy, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    write_reward(output, 0.0)
    (output / "summary.json").write_text('{"status": "running", "reward": 0.0}\n')
    try:
        config = evaluation_config(**json.loads(Path(config_path).read_text()))
        directory = Path(tempfile.mkdtemp(prefix="evaluation-", dir=output))
        summary = evaluate(policy, directory / "run", **config)
        summary["status"] = "completed"
        summary["evaluation_directory"] = str(directory.relative_to(output) / "run")
        (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        write_reward(output, summary["reward"])
        return summary
    except Exception as error:
        failure = {"status": "failed", "reward": 0.0, "error": f"{type(error).__name__}: {error}"}
        write_reward(output, 0.0)
        (output / "summary.json").write_text(json.dumps(failure, indent=2) + "\n")
        return failure


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    export = commands.add_parser("export", help="Create a self-contained Harbor task dataset.")
    export.add_argument("--output", type=Path, required=True, help="New task dataset directory.")
    export.add_argument("--tasks", type=int, default=1)
    add_evaluation_arguments(export)
    verifier = commands.add_parser("verify", help="Run the Harbor reward verifier locally.")
    verifier.add_argument("--config", type=Path, required=True)
    verifier.add_argument("--policy", required=True)
    verifier.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "verify":
        print(json.dumps(verify(args.config, args.policy, args.output), indent=2))
    else:
        try:
            result = export_tasks(args.output, tasks=args.tasks, **settings_from_args(args))
        except (OSError, ValueError) as error:
            parser.exit(2, f"{error}\n")
        print(result)


if __name__ == "__main__":
    main()
