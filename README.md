# Counterplay

A local-first Pokémon TCG research studio built around the official CABT engine.
Run baseline matchups, version decks, compare results, and inspect every selection.
There is no Kaggle submission or export workflow.

## Run locally

Requires Node.js 20.19+ (or 22.12+) and Python 3.11+ with [uv](https://docs.astral.sh/uv/).

```sh
uv sync --locked
npm ci
```

In one terminal:

```sh
uv run --locked python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

In another:

```sh
npm run dev
```

Open **http://127.0.0.1:5173**. Create an experiment to run real engine matches.
No sample results are fabricated or inserted automatically.

For a single-server production build:

```sh
npm run build
uv run --locked python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000**. Build before starting the API so it can discover `dist/`.
Keep the API bound to localhost: this personal workspace has no authentication.

## What works

- **Experiments:** independent BO1 games, frozen agent/deck/engine fingerprints,
  configurable selection and wall-clock budgets, a local queue, live progress,
  and cancellation after the current game.
- **Agents:** uniform-subset random and first-choice baselines. Their source is in
  `backend/agents.py`; the registry and API currently support these two policies.
- **Deck lab:** native card lookup, 60-card validation, copy/basic/ACE SPEC checks,
  immutable named versions, and complete deck snapshots in each experiment.
  The engine remains the final authority and can reject a deck at battle start.
- **Inspector:** recorded board state, observed hand, HP and energy, every legal
  choice and selected index, policy diagnostics, engine events, raw observations,
  playback, keyboard stepping, persistent bookmarks, and full replay JSON downloads.
- **Results:** wins/losses/draws, candidate win rates, 95% Wilson intervals,
  policy decision latency, failures, and capped games.
- **Persistence:** SQLite metadata plus compressed full JSON replays under `data/`.
  Set `TCG_DATA_DIR` to use another directory. Restarted unfinished experiments
  are marked interrupted, never silently reported as completed.

## Research semantics

Candidate is always player 0; opponent is player 1. Successive games alternate
**which player gets to choose first or second**, not a guaranteed starting seat.
The recorded `first_player` is the actual seat chosen in each game.

The policy seed controls only the random agent, with separate streams per player
and game. **CABT shuffles and coin flips are not seeded by this interface.**
Playback uses saved observations; it does not rerun or restore native engine state.
The inspector follows the observing agent at each decision and never reconstructs
hidden cards. Raw trace downloads contain both players' observations across time,
so they are research artifacts, not safe inputs for an active opponent.

Win rate is candidate wins divided by completed games (draws stay in the
denominator). Failed and budget-capped games are excluded, not relabeled draws.
The displayed interval is a descriptive per-experiment Wilson interval.
Do not treat comparisons across different decks, opponents, or budgets as
controlled improvements. Baseline agents are intentionally simple, not competitive.

## Harbor and reinforcement learning

Evaluate a Python policy over many isolated games with a failure-inclusive
win-rate reward, or export standalone Harbor tasks:

```sh
uv run --locked python -m backend.rl \
  --policy examples/policies/random_policy.py --games 1024 --workers 8 \
  --output data/rl/checkpoint-001

uv run --locked python -m backend.harbor export \
  --tasks 4 --games 256 --workers 4 --output data/harbor-tasks
```

The integration includes a `reset`/`step` environment, legal-action validation,
candidate-only rollout exports, frozen policy/engine/configuration fingerprints,
and `backend.harbor_agent:PolicyAgent` for existing trained policy files.
Reward is **wins / all scheduled games**; failures and caps earn zero rather
than disappearing. This is the CABT rules/card pool, not current Standard.
See [the Harbor/RL guide](docs/HARBOR.md) for the policy contract, Harbor commands,
training semantics, and limitations.

## Architecture

```text
React / TypeScript / Vite
          |
     FastAPI API
          |
   single local run queue
          |
  fresh subprocess per game
          |
   official CABT ctypes engine
          |
  SQLite + gzip JSON artifacts
```

`kaggle-environments==1.33.3` is pinned in the lockfile. A uv dependency-metadata
override deliberately omits unrelated environment dependencies: the adapter loads
only the self-contained CABT `cg/sim.py` and `cg/game.py` wrappers, never imports
the global environment registry, and calls the native card/attack metadata API.
This project does **not** implement replacement TCG rules or vendor the engine.
The engine package's bundled platform binaries determine platform availability.

The API is a **single-process local service**; do not start multiple Uvicorn
workers against the same data directory. Each match gets a separate OS process
because CABT's wrapper uses process-global battle state. Current baselines run
inside that match process; this is crash isolation, not a sandbox for untrusted code.
Worker crashes and timeouts are recorded as failures. A killed/timed-out worker
cannot supply its in-memory partial trace; previously saved games remain intact.

## Validation

```sh
uv run --locked python -m pytest
uv run --locked ruff check backend tests examples/policies
uv run --locked ruff format --check backend tests examples/policies
npm run check
npm run format:check
npm run build
npx playwright install chromium
npm run test:e2e
```

Backend tests execute the real native engine. Browser tests start isolated servers
on ports 8001 and 5174 and use `data/e2e/`, separate from normal workspace data.

## Next milestones

Custom versioned agent registration, frozen evaluation suites and controlled
candidate comparisons, richer matchup analysis, and counterfactual search with
explicit hidden-state assumptions. These are not implemented in the initial slice.

## Upstream

- [CABT documentation](https://matsuoinstitute.github.io/cabt/)
- [Official environment source](https://github.com/Kaggle/kaggle-environments/tree/master/kaggle_environments/envs/cabt)
- [Competition overview](https://www.kaggle.com/competitions/the-pokemon-company-ptcg-ai-battle-challenge-playground/overview)

Independent research software, not affiliated with or endorsed by Pokémon, Kaggle,
or the CABT authors. Upstream code, native binaries, and card data retain their
respective licenses and rights. Card displays are metadata-based, not official art.
