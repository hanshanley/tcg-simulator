# Harbor / RL correctness audit

Date: November 16, 2026.

Scope: interactive episode lifecycle, legal actions, candidate observations,
worker isolation and deadlines, result validation, failure-inclusive rewards,
frozen artifacts, and the exported Harbor verifier/agent contract. This is a
correctness audit, not a penetration test or a certification of upstream rules.

## Confirmed defects and fixes

All four findings below were reproduced and fixed.

| Priority | Finding and impact | Fix |
| --- | --- | --- |
| P1 | `backend.harbor.verify` left an existing `reward.json` unchanged. Harbor prefers JSON over TXT, so a failed rerun could retain an earlier positive score. An earlier successful summary also remained visible during evaluation. | Reset both reward formats to zero and the summary to `running` before setup/evaluation. Atomically replace the canonical JSON reward; write consistent final scores and explicit `completed`/`failed` status. Reject nonfinite or out-of-range rewards. |
| P2 | `backend.rl_worker.load_policy` executed custom modules without registering them in `sys.modules`. A valid annotated dataclass policy failed during import and lost every game. | Register the module before executing it, restoring any previous registration if execution fails. |
| P2 | `backend.rl.reward_summary` accepted malformed outcomes that the worker reader rejected: `False` counted as player 0, missing winners became draws, and unfinished results could carry a winner. | Share strict outcome validation with the worker-result reader. Require an explicit winner, integer 0/1 or null, and no winner on unfinished games. |
| P2 | Batch engine checks skipped missing/null provenance. A completed result with no engine identity could count as a win. | Require matching native-engine provenance for completed/capped results. Invalid provenance becomes a failed game with zero reward and remains in the denominator. |

Focused regressions cover each reproduction, interruption after score reset,
matching successful reward formats, invalid numeric rewards, and the exact
exported verifier entrypoint. Nine cases failed before the production fixes;
the focused selector now passes all 13 cases.

## Observation and lifecycle checks

The candidate always acts as player 0. Real native episodes check that the
opponent hand is masked and identified draw events belong to the candidate.
Terminal observations controlled by the opponent are withheld. Recorded
observations are copied before policy calls, so policy mutation cannot erase
the training trace. Native logs already carry observer-filtered history; the
adapter does not concatenate private logs from opposite player perspectives.

The upstream `search_begin_input` observation field is preserved, not treated
as a newly discovered leak: CABT documents it as search initialization input,
with hidden-state predictions supplied by the search caller. This does not
constitute an exhaustive audit of the native binary's information boundaries.

Existing tests also exercise decision caps, terminal precedence, timeouts,
invalid actions, native-state cleanup/reset, and refusal of simultaneous native
environments in the same process. Worker process groups are terminated on
completion/timeout; the parent reaps its direct worker, not arbitrary descendants.

## Validation

- Full local Python suite: **54 passed, 1 skipped**. The optional module requires
  Harbor, which is intentionally not a simulator dependency.
- Ruff lint and format checks passed for `backend`, `tests`, and example policies.
- Fresh native batch: **1,024 completed**, **338 wins**, **686 losses**,
  **0 failures**, **0 caps**, **0 draws**, reward **0.330078125**.
- Independently checked every game ID, per-game result/configuration, outcome
  reward, engine identity, frozen policy SHA-256, all seven frozen runtime
  hashes, and the recomputed summary. Each opponent/choice-order stratum
  contained exactly 256 games.
- The standalone exported verifier is exercised outside the repository working
  directory. CI additionally runs actual Harbor 0.26 contracts and a Docker
  policy-agent trial with a separate verifier; it requires agreement between
  Harbor's collected score, evaluation summaries, JSON reward, and TXT reward.

Reproduce the local checks:

```sh
uv run --locked python -m pytest
uv run --locked ruff check backend tests examples/policies
uv run --locked ruff format --check backend tests examples/policies
uv run --locked python -m backend.rl \
  --policy examples/policies/random_policy.py \
  --games 1024 --workers 8 --opponents random first \
  --output data/rl/new-audit-validation
```

Batch rewards vary because native shuffles and coin flips are not seedable.
The reported win rate validates execution/accounting, not policy strength.
The local batch artifacts remain under ignored `data/rl/`; CI retains its
Harbor trial as a workflow artifact.

## Boundaries that remain intentional

This adapter uses the pinned CABT card pool, not current tournament Standard.
It is a Gym-style environment/evaluator, not a training algorithm or a
registered fixed-action-space Gymnasium environment. Harbor submissions are one
self-contained Python file; external model files and agent-installed packages
do not transfer automatically. Policies are trusted code: subprocesses are
crash/timeout isolation, not a security sandbox or anti-cheating guarantee.
Exact native replay and comprehensive correctness of all upstream card effects
are outside this audit's claims. No website deployment is part of this change.

## Follow-up fixes: November 17, 2026

Four additional correctness defects were reproduced and fixed:

| Finding | Reproduction | Fix |
| --- | --- | --- |
| Native card-ID wrapping | Adding or subtracting `2**32` from every card ID still ran the original deck through the C binding. Recorded input IDs therefore did not describe the cards played. | Share nonnegative signed-32-bit deck validation between the RL environment and studio worker, before passing IDs to native code. Unknown but representable IDs remain subject to the native engine's deck validation. |
| Concurrent cold initialization | Eight concurrent cold loads executed the native-wrapper initializer eight times in a mocked-loader reproduction. The cached function alone did not serialize first calls. | Serialize access to the cached initializer, preserving one native-wrapper instance and consistent module pairs per process. The regression uses a mocked loader rather than racing the real native initializer. |
| Exported verifier import shadowing | Running the exported script from a directory containing an unrelated `backend/harbor.py` imported that file instead of the exported runtime. | Launch Python with safe-path mode and the explicit exported runtime path. Regression executes the actual verifier from a shadowing directory. |
| Relative output loses a valid reward | On Python 3.12, `verify(..., output="logs")` completed evaluation but failed to relate an absolute temporary directory to the relative output path, reporting zero reward. | Resolve the output directory before creating artifacts. Check both direct verification and the standalone script with caller-relative paths. |

Validation: **59 tests passed, 1 optional Harbor module skipped**; Ruff lint and
format checks passed. Six regression cases failed before the initial fixes; a
separate relative-output regression then reproduced the fourth defect before
its fix. Representable unknown IDs `0`, `999999`, and `2147483647` were also
checked in isolated workers: each failed explicitly as a rejected deck, without
a native crash.

A fresh **1,024-game** batch completed with **349 wins**, **675 losses**,
**zero failures/caps/draws**, and reward **0.3408203125**. Every result,
configuration, schedule entry, policy/runtime hash, engine identity, and
aggregate reward was independently checked; each opponent/choice-order stratum
contained 256 games. Local artifacts:
`data/rl/harbor-followup-20261117-1024/`.
