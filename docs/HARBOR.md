# Harbor / reinforcement-learning integration

The adapter exposes the existing **CABT** simulator as an interactive episode,
a parallel policy evaluator, and a self-contained Harbor task dataset. It does
not implement a training algorithm, replace CABT's rules, or use the separate
`pokemon-tcg-tournament` project. This is the pinned CABT card pool, **not current
tournament Standard**.

## Evaluate a policy locally

```sh
uv sync --locked
uv run --locked python -m backend.rl \
  --policy examples/policies/random_policy.py \
  --games 1024 --workers 8 \
  --opponents random first \
  --rollouts \
  --output data/rl/checkpoint-001
```

`--policy` accepts `random`, `first`, or a self-contained Python file defining:

```python
def select(observation: dict, rng) -> list[int]:
    selection = observation["select"]
    maximum = min(selection["maxCount"], len(selection["option"]))
    count = rng.randint(selection["minCount"], maximum)
    return rng.sample(range(len(selection["option"])), count)
```

Replace this function with feature extraction and inference from your trained
policy. Return distinct zero-based **option indices**, not card IDs or action
objects. Optional/empty/multiple selections respect the native `minCount` and
`maxCount`. The supplied `rng` is a `random.Random` instance. Module globals
reset between games; policies may retain state across decisions within a game.
An evaluation freezes a copy of the policy file before launching workers.
Additional model libraries must already be installed in the evaluation runtime.

Candidate is always player 0. Opponents alternate in pairs: random with each
choice order, then first-choice with each choice order. Multiples of four games
give the default two opponents equal representation in each choice order.
`reverse` changes who chooses whether to play first/second; it does not force
the actual first player. Every game records both.

Each game runs in a fresh process. `--workers` bounds concurrent games, and the
queue and aggregation do not hold every game in memory. The wall-clock limit
includes policy imports, native initialization, and all policy calls. The
decision limit counts **both players'** native selections. Worker process groups
are reaped on completion/timeout; the evaluator targets Linux and macOS.

## Rewards and artifacts

**Reward = candidate wins / all scheduled games**, a float in `[0, 1]`.
Multiply by 100 for the winning percentage.

Draws, capped games, invalid actions, exceptions, native crashes, and timeouts
earn zero and remain in the denominator. This prevents a policy from improving
its score by failing on difficult games. The studio UI's existing
completed-games-only metric is unchanged; the evaluator also reports that
conditional rate explicitly as a diagnostic, never as the training reward.

Every evaluation creates a new directory containing:

| Artifact | Contents |
| --- | --- |
| `manifest.json` | Frozen decks, budgets, opponent schedule, policy hash, runtime source hashes, native engine/platform identity, Python version |
| `policy.py` | Frozen submitted file, when evaluating a custom policy |
| `summary.json` | Reward, wins/losses/draws, caps/failures, completion rate, descriptive 95% Wilson interval |
| `games.jsonl` | One result and complete match protocol per scheduled game |
| `games/<id>/` | Per-game configuration, result, worker log, optional candidate transitions |

With `--rollouts`, `games/<id>/rollout.jsonl` records each candidate observation,
selected action, next candidate observation, terminal/truncation flags, and
sparse per-game reward. Opponent decisions are automatic, not logged into these
rollouts. A terminal/capped observation is `null` when native control has passed
to the opponent, avoiding accidental exposure of the opponent's private hand.
Use completed episodes for training or inspect the result before consuming a
partial trace from a failed game.

**Policy seeds do not seed native CABT shuffles or coin flips.** Frozen inputs
and traces permit audit and playback, not exact stochastic game reruns. Repeat
evaluations and use sufficiently large, comparable batches. The Wilson interval
is descriptive; it is not proof of improvement across different opponents,
decks, budgets, or training checkpoints.

Policies are trusted local code. A worker is crash/timeout isolation, **not a
security sandbox**. Harbor containers provide the outer execution environment.

## Interactive episodes

```python
import random

from backend.rl_env import CABTEnv

rng = random.Random(42)
with CABTEnv(opponent="random", max_decisions=2000) as env:
    observation, info = env.reset(seed=42)
    while info["status"] == "running":
        selection = observation["select"]
        maximum = min(selection["maxCount"], len(selection["option"]))
        count = rng.randint(selection["minCount"], maximum)
        action = rng.sample(range(len(selection["option"])), count)
        observation, reward, terminated, truncated, info = env.step(action)
```

The tuple convention is Gym-style, but this is dependency-free, not a registered
Gymnasium environment with a fixed action space. A trainer must encode the
variable-length legal options appropriately. Reward is 1 only for a terminal
candidate win; intermediate steps, losses, draws and truncations return 0.
The batch evaluator averages those win indicators over every scheduled game.

CABT has process-global native state: use **one active environment per OS
process**, always close it, and use process-based vectorization rather than
multiple native environments in one process. A second active instance is
explicitly rejected. The parallel evaluator handles this isolation for you.

## Run through Harbor

The adapter targets Harbor **0.26.0**, task schema **1.4**. Harbor requires Python
3.12+ and a supported container/sandbox provider. Docker is the default local
provider; it must be installed and running. Harbor is deliberately optional:
the simulator and local training/evaluation do not depend on it.

Export four standalone tasks, each evaluating 256 games:

```sh
uv run --locked python -m backend.harbor export \
  --tasks 4 --games 256 --workers 4 --rollouts \
  --output data/harbor-tasks
```

Task seeds use disjoint policy-RNG streams. Outputs contain complete runtime
sources, frozen decks/configuration, a Dockerfile that installs the pinned
upstream engine, instructions, an example solution, and a verifier. No local
database, web server, Kaggle account, or external model API is required.

From the repository root, evaluate an existing policy:

```sh
PYTHONPATH="$PWD" uvx --python 3.12 --from harbor==0.26.0 harbor run \
  --path data/harbor-tasks \
  --agent backend.harbor_agent:PolicyAgent \
  --ak policy_path="$PWD/examples/policies/random_policy.py" \
  --n-concurrent 2 \
  --jobs-dir data/harbor-jobs
```

`PolicyAgent` freezes/uploads the policy file; Harbor runs the verifier and
collects its reward. Alternatively, use any Harbor coding agent to write
`/app/policy.py` following the task instructions. The included oracle solution
is just a random-policy smoke test, **not** a policy guaranteed to earn reward 1.

Verification uses a **separate environment**, transferring only the declared
`/app/policy.py` artifact. Dependencies/code installed or modified by a coding
agent are not transferred. Extend the exported image in advance if your policy
needs PyTorch or other packages; the initial contract is one self-contained
policy file, not a multi-file model/weights bundle.

Each verifier writes `/logs/verifier/reward.txt`, a full evaluation directory,
and `/logs/verifier/summary.json`. A verification/setup error writes reward zero
plus an explicit error, never a fabricated successful game. Tasks can run
independently or concurrently; account for `task workers × concurrent trials`
when sizing compute. Harbor's mean task reward equals overall game win rate
when tasks contain equal numbers of games.

Test an exported task's exact verifier without Harbor or Docker:

```sh
uv run --locked bash data/harbor-tasks/tcg-policy-0000/tests/test.sh \
  "$PWD/examples/policies/random_policy.py" "$PWD/data/verifier-smoke"
```

Test the Python integration and optional actual Harbor class contracts:

```sh
uv run --locked python -m pytest
uv run --locked ruff check backend tests examples/policies
uv run --locked ruff format --check backend tests examples/policies
PYTHONPATH="$PWD" uv run --no-project --python 3.12 \
  --with harbor==0.26.0 --with pytest==8.4.2 \
  python -m pytest tests/test_harbor_contract.py
```
