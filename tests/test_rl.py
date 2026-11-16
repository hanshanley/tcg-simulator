import hashlib
import json
import os
import random
import subprocess
import sys
import tomllib
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.agents import choose
from backend.engine import starter_deck
from backend.harbor import export_tasks, verify
from backend.rl import evaluate, evaluation_config, game_config, reward_summary
from backend.rl_env import CABTEnv, validate_action


@pytest.mark.parametrize("action", [[True], [0, 0], [-1], [3], [], [0, 1, 2], (0,)])
def test_invalid_actions_are_rejected(action):
    observation = {"select": {"minCount": 1, "maxCount": 2, "option": [1, 2, 3]}}
    with pytest.raises(ValueError):
        validate_action(action, observation)


def test_optional_empty_action_is_legal():
    validate_action([], {"select": {"minCount": 0, "maxCount": 0, "option": []}})


def test_real_episode_is_candidate_perspective_and_reset_releases_engine():
    rng = random.Random(7)
    with CABTEnv() as env:
        for seed in (42, 44):
            observation, info = env.reset(seed=seed)
            assert observation["current"]["yourIndex"] == 0
            assert info["native_rng_seeded"] is False
            assert info["policy_seed"] == seed
            old_count = env.decisions
            with pytest.raises(ValueError):
                env.step([999999])
            assert env.decisions == old_count
            for _ in range(2000):
                action, _ = choose("random", observation, rng)
                observation, reward, terminated, truncated, info = env.step(action)
                assert observation is None or observation["current"]["yourIndex"] == 0
                assert reward == float(terminated and info["winner"] == 0)
                if terminated or truncated:
                    break
            else:
                pytest.fail("Episode did not honor its native decision limit.")
            assert info["first_player"] in (0, 1)
            with pytest.raises(RuntimeError):
                env.step([])


def test_concurrent_native_env_is_refused_without_corrupting_owner():
    with CABTEnv() as first, CABTEnv() as second:
        observation, _ = first.reset()
        with pytest.raises(RuntimeError, match="separate OS processes"):
            second.reset()
        action, _ = choose("first", observation, random.Random(1))
        first.step(action)
    with CABTEnv() as fresh:
        fresh.reset()


def test_rejected_deck_frees_native_state():
    with CABTEnv(decks=[[3] * 60, starter_deck()]) as env:
        with pytest.raises(ValueError, match="rejected deck"):
            env.reset()
    with CABTEnv() as fresh:
        fresh.reset()


def test_terminal_opponent_observation_is_not_exposed_and_completion_beats_cap(monkeypatch):
    import backend.rl_env as module

    def observation(player, result):
        return {
            "current": {"yourIndex": player, "result": result, "firstPlayer": 0},
            "select": {"minCount": 0, "maxCount": 0, "option": []},
            "private_hand": f"player-{player}-secret",
        }

    battle = SimpleNamespace(battle_ptr=None, lib=None)

    def start(*args):
        battle.battle_ptr = 1
        return observation(0, -1), SimpleNamespace(errorPlayer=-1)

    sim = SimpleNamespace(Battle=battle, get_lib=lambda version: None)
    game = SimpleNamespace(
        battle_start=start,
        battle_select=lambda action: observation(1, 1),
        battle_finish=lambda: None,
    )
    monkeypatch.setattr(module, "load_engine", lambda: (sim, game))
    with CABTEnv(max_decisions=1) as env:
        env.reset()
        visible, reward, terminated, truncated, info = env.step([])
        assert visible is None
        assert reward == 0
        assert terminated and not truncated
        assert info["status"] == "completed" and info["winner"] == 1
        assert "secret" not in json.dumps(info)


def test_reward_denominator_includes_every_scheduled_outcome():
    summary = reward_summary(
        [
            {"status": "completed", "winner": 0},
            {"status": "completed", "winner": 1},
            {"status": "completed", "winner": None},
            {"status": "failed", "winner": None},
            {"status": "capped", "winner": None},
        ]
    )
    assert summary["reward"] == summary["win_rate"] == pytest.approx(0.2)
    assert summary["completed_game_win_rate"] == pytest.approx(1 / 3)
    assert summary["completion_rate"] == pytest.approx(3 / 5)
    assert summary["scheduled_games"] == 5
    assert summary["win_rate_ci95"][0] < 0.2 < summary["win_rate_ci95"][1]


@pytest.mark.parametrize(
    "settings",
    [
        {"games": 0},
        {"workers": True},
        {"policy_seed": True},
        {"max_decisions": -1},
        {"timeout_seconds": float("nan")},
        {"timeout_seconds": float("inf")},
        {"timeout_seconds": 0},
        {"opponents": []},
        {"opponents": ["missing"]},
        {"decks": [[True] * 60, starter_deck()]},
        {"rollouts": "yes"},
    ],
)
def test_invalid_evaluation_protocol_is_refused(settings):
    with pytest.raises(ValueError):
        evaluation_config(**settings)


def test_opponent_schedule_pairs_both_choice_orders_and_unique_rng_streams():
    config = evaluation_config(games=8, policy_seed=100)
    games = [game_config(config, index) for index in range(8)]
    assert [(row["opponent"], row["reverse"]) for row in games] == [
        ("random", False),
        ("random", True),
        ("first", False),
        ("first", True),
    ] * 2
    streams = [seed for row in games for seed in (row["policy_seed"], row["policy_seed"] + 1)]
    assert len(set(streams)) == 16


def test_real_parallel_policy_batch_pins_inputs_and_candidate_only_rollouts(tmp_path):
    source = Path(__file__).resolve().parents[1] / "examples/policies/random_policy.py"
    output = tmp_path / "evaluation"
    summary = evaluate(str(source), output, games=4, workers=2, rollouts=True)
    games = [json.loads(line) for line in (output / "games.jsonl").read_text().splitlines()]
    assert len(games) == len({row["game"] for row in games}) == 4
    assert summary["scheduled_games"] == 4
    assert summary["completed"] == 4
    assert summary["failed"] == 0
    assert summary["reward"] == sum(row["reward"] for row in games) / 4
    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["policy"]["artifact_sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert (output / "policy.py").read_bytes() == source.read_bytes()
    assert manifest["engine"]["rules_version"] == 2
    assert manifest["native_rng_seeded"] is False
    for name, digest in manifest["runtime_sha256"].items():
        assert (
            hashlib.sha256((output / "runtime/backend" / name).read_bytes()).hexdigest() == digest
        )
    for row in games:
        path = output / "games" / f"{row['game']:07d}" / "rollout.jsonl"
        transitions = [json.loads(line) for line in path.read_text().splitlines()]
        assert transitions
        assert transitions[-1]["terminated"]
        for transition in transitions:
            assert transition["observation"]["current"]["yourIndex"] == 0
            following = transition["next_observation"]
            assert following is None or following["current"]["yourIndex"] == 0
            validate_action(transition["action"], transition["observation"])
    with pytest.raises(FileExistsError):
        evaluate("random", output, games=1)


def test_invalid_policy_actions_fail_without_disappearing_from_reward(tmp_path):
    policy = tmp_path / "invalid.py"
    policy.write_text("def select(observation, rng):\n    return [True]\n")
    summary = evaluate(str(policy), tmp_path / "eval", games=3, workers=2)
    assert summary["failed"] == summary["scheduled_games"] == 3
    assert summary["completed"] == 0 and summary["reward"] == 0
    results = [
        json.loads(line) for line in (tmp_path / "eval/games.jsonl").read_text().splitlines()
    ]
    assert all("Python integer" in row["error"] for row in results)


def test_policy_mutation_does_not_destroy_recorded_observations(tmp_path):
    policy = tmp_path / "mutating.py"
    policy.write_text(
        "def select(observation, rng):\n"
        "    import backend\n"
        "    assert '/runtime/backend/' in backend.__file__.replace('\\\\', '/')\n"
        "    selection = observation['select']\n"
        "    result = list(range(selection['minCount']))\n"
        "    observation.clear()\n"
        "    return result\n"
    )
    output = tmp_path / "eval"
    summary = evaluate(str(policy), output, games=1, rollouts=True)
    assert summary["completed"] == 1
    transitions = (output / "games/0000000/rollout.jsonl").read_text().splitlines()
    assert transitions
    for line in transitions:
        transition = json.loads(line)
        validate_action(transition["action"], transition["observation"])


def test_real_policy_timeout_is_bounded_and_penalized(tmp_path):
    policy = tmp_path / "hang.py"
    policy.write_text("while True:\n    pass\n")
    summary = evaluate(str(policy), tmp_path / "eval", games=2, workers=2, timeout_seconds=0.25)
    assert summary["failed"] == 2 and summary["reward"] == 0
    results = [
        json.loads(line) for line in (tmp_path / "eval/games.jsonl").read_text().splitlines()
    ]
    assert all("wall-clock" in row["error"] for row in results)


def test_capped_games_are_not_draws_or_excluded(tmp_path):
    summary = evaluate("random", tmp_path / "eval", games=2, max_decisions=1)
    assert summary["capped"] == summary["scheduled_games"] == 2
    assert summary["completed"] == summary["draws"] == 0
    assert summary["reward"] == 0


def test_exported_verifier_runs_standalone_from_exact_entrypoint(tmp_path):
    exported = export_tasks(tmp_path / "tasks", tasks=2, games=4, workers=2, rollouts=True)
    task = exported / "tcg-policy-0000"
    config = tomllib.loads((task / "task.toml").read_text())
    assert config["verifier"]["environment_mode"] == "separate"
    first = json.loads((task / "tests/evaluation.json").read_text())
    second = json.loads((exported / "tcg-policy-0001/tests/evaluation.json").read_text())
    assert second["policy_seed"] >= first["policy_seed"] + first["games"] * 2
    empty_cwd = tmp_path / "empty-cwd"
    empty_cwd.mkdir()
    logs = tmp_path / "logs"
    subprocess.run(
        [
            "bash",
            str(task / "tests/test.sh"),
            str(task / "environment/example_policy.py"),
            str(logs),
        ],
        cwd=empty_cwd,
        env={**os.environ, "PATH": f"{Path(sys.executable).parent}:{os.environ['PATH']}"},
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    summary = json.loads((logs / "summary.json").read_text())
    assert summary["scheduled_games"] == summary["completed"] == 4
    assert float((logs / "reward.txt").read_text()) == summary["reward"]
    artifacts = logs / summary["evaluation_directory"]
    assert (artifacts / "manifest.json").is_file()
    assert len((artifacts / "games.jsonl").read_text().splitlines()) == 4
    with pytest.raises(FileExistsError):
        export_tasks(exported, games=1)


def test_verifier_missing_submission_always_writes_zero_reward(tmp_path):
    config = tmp_path / "config.json"
    config.write_text(json.dumps(evaluation_config(games=1)))
    output = tmp_path / "logs"
    summary = verify(config, str(tmp_path / "missing.py"), output)
    assert summary["reward"] == 0 and "error" in summary
    assert float((output / "reward.txt").read_text()) == 0
