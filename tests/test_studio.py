import random
import time

import pytest
from fastapi.testclient import TestClient

from backend.agents import choose
from backend.app import create_app
from backend.engine import starter_deck
from backend.store import Store, summarize


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path)) as instance:
        yield instance


def create_run(client, **overrides):
    deck = client.get("/api/decks").json()[0]
    return client.post(
        "/api/experiments",
        json={
            "name": "Baseline experiment",
            "deck_ids": [deck["id"], deck["id"]],
            "games": 2,
            **overrides,
        },
    )


def wait_for_run(client, experiment_id):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        experiment = client.get(f"/api/experiments/{experiment_id}").json()
        if experiment["status"] not in ("queued", "running", "cancelling"):
            return experiment
        time.sleep(0.05)
    pytest.fail("Native experiment did not finish in time")


def test_real_experiment_records_legal_decisions_and_survives_restart(client, tmp_path):
    response = create_run(client)
    assert response.status_code == 201
    experiment = wait_for_run(client, response.json()["id"])
    assert experiment["status"] == "completed"
    assert experiment["summary"]["completed"] == 2
    assert experiment["summary"]["failed"] == 0
    assert experiment["engine"]["rules_version"] == 2
    assert len(experiment["engine"]["native_sha256"]) == 64
    assert all(len(deck["cards"]) == 60 for deck in experiment["decks"])
    assert [game["protocol"]["reverse"] for game in experiment["games"]] == [False, True]
    game_id = experiment["games"][0]["id"]
    replay = client.get(f"/api/games/{game_id}").json()
    assert replay["final_observation"]["current"]["result"] >= 0
    assert replay["decisions"]
    for decision in replay["decisions"]:
        selection = decision["observation"]["select"]
        assert selection["minCount"] <= len(decision["selected"]) <= selection["maxCount"]
        assert len(set(decision["selected"])) == len(decision["selected"])
        assert all(0 <= index < len(selection["option"]) for index in decision["selected"])
        assert decision["latency_ms"] >= 0
    assert (
        client.put(
            f"/api/games/{game_id}/bookmarks/0", json={"label": "Investigate opening"}
        ).status_code
        == 200
    )
    saved = Store(tmp_path).replay(game_id)
    assert saved["bookmarks"] == [{"decision": 0, "label": "Investigate opening"}]
    assert saved["decisions"] == replay["decisions"]
    assert (
        client.put(f"/api/games/{game_id}/bookmarks/999999", json={"label": "Invalid"}).status_code
        == 422
    )
    assert client.put(f"/api/games/{game_id}/bookmarks/0", json={"label": ""}).status_code == 200
    assert Store(tmp_path).replay(game_id)["bookmarks"] == []


def test_decision_cap_is_not_reported_as_draw(client):
    experiment = wait_for_run(client, create_run(client, games=1, max_decisions=1).json()["id"])
    assert experiment["status"] == "completed"
    assert experiment["games"][0]["status"] == "capped"
    assert experiment["summary"]["capped"] == 1
    assert experiment["summary"]["completed"] == 0
    assert experiment["summary"]["draws"] == 0
    assert experiment["summary"]["win_rate"] is None


def test_deck_versions_are_immutable_and_invalid_decks_rejected(client):
    original = client.get("/api/decks").json()[0]
    payload = {
        "name": original["name"],
        "cards": original["cards"],
        "description": "Second version",
    }
    updated = client.post("/api/decks", json=payload)
    assert updated.status_code == 201
    assert updated.json()["version"] == 2
    assert updated.json()["id"] != original["id"]
    assert updated.json()["sha256"] == original["sha256"]
    assert client.get("/api/decks").json()[-1] == original
    assert client.post("/api/decks", json={**payload, "cards": [3] * 60}).status_code == 422
    assert client.post("/api/decks", json={**payload, "cards": [999999] * 60}).status_code == 422
    assert client.post("/api/decks", json={**payload, "cards": [721] * 60}).status_code == 422
    assert client.post("/api/decks", json={**payload, "cards": [True] * 60}).status_code == 422
    assert client.post("/api/decks", json={**payload, "name": "   "}).status_code == 422


def test_invalid_experiment_and_missing_artifacts(client):
    assert create_run(client, agent_ids=["unknown", "random"]).status_code == 422
    assert create_run(client, deck_ids=["missing", "missing"]).status_code == 422
    assert create_run(client, games=0).status_code == 422
    assert client.get("/api/experiments/missing").status_code == 404
    assert client.get("/api/games/missing").status_code == 404
    assert client.get("/api/games/..%2Freplays").status_code == 404


def test_summary_excludes_failures_and_caps_but_includes_draws():
    summary = summarize(
        [
            {"status": "completed", "winner": 0},
            {"status": "completed", "winner": 1},
            {"status": "completed", "winner": None},
            {"status": "failed", "winner": None},
            {"status": "capped", "winner": None},
        ]
    )
    assert summary["win_rate"] == pytest.approx(1 / 3)
    assert (summary["wins"], summary["losses"], summary["draws"]) == (1, 1, 1)
    assert summary["failed"] == summary["capped"] == 1
    assert summary["win_rate_ci"][0] < summary["win_rate"] < summary["win_rate_ci"][1]


def test_baselines_handle_optional_empty_and_multi_select_bounds():
    for agent in ("random", "first"):
        for minimum, maximum, option_count in [(0, 0, 0), (0, 3, 5), (2, 4, 4)]:
            observation = {
                "select": {
                    "minCount": minimum,
                    "maxCount": maximum,
                    "option": [{}] * option_count,
                }
            }
            selected, _ = choose(agent, observation, random.Random(42))
            assert minimum <= len(selected) <= maximum
            assert len(set(selected)) == len(selected)


def test_restart_marks_unfinished_runs_interrupted(tmp_path):
    from backend.agents import agent_catalog
    from backend.runner import Runner

    store = Store(tmp_path)
    deck_id = store.decks()[0]["id"]
    experiment = store.create_experiment(
        {"name": "Unfinished", "deck_ids": [deck_id, deck_id]},
        {},
        agent_catalog(),
    )
    runner = Runner(store)
    try:
        assert store.experiment(experiment["id"])["status"] == "interrupted"
    finally:
        runner.close()


def test_native_invalid_deck_failure_is_recorded(tmp_path):
    from backend.runner import Runner

    runner = Runner(Store(tmp_path))
    try:
        result = runner._match(
            {
                "agents": ["random", "first"],
                "decks": [[3] * 60, starter_deck()],
                "reverse": False,
                "policy_seed": 42,
                "max_decisions": 10,
            },
            10,
        )
        assert result["status"] == "failed"
        assert "deck" in result["error"].lower()
        assert result["winner"] is None
    finally:
        runner.close()


def test_cancellation_keeps_current_game_and_skips_queued_games(client, monkeypatch):
    import threading

    started = threading.Event()
    release = threading.Event()
    calls = []

    def blocked_match(protocol, timeout):
        calls.append(protocol)
        started.set()
        assert release.wait(5)
        return {
            "status": "capped",
            "winner": None,
            "decisions": [],
            "duration_ms": 0,
        }

    monkeypatch.setattr(client.app.state.runner, "_match", blocked_match)
    running = create_run(client, games=5).json()
    try:
        assert started.wait(5)
        queued = create_run(client, games=5).json()
        queued_cancel = client.post(f"/api/experiments/{queued['id']}/cancel").json()
        assert queued_cancel["status"] == "cancelled"
        running_cancel = client.post(f"/api/experiments/{running['id']}/cancel").json()
        assert running_cancel["status"] == "cancelling"
    finally:
        release.set()
    stopped = wait_for_run(client, running["id"])
    assert stopped["status"] == "cancelled"
    assert len(stopped["games"]) == 1
    assert len(calls) == 1
    assert client.get(f"/api/experiments/{queued['id']}").json()["games"] == []


def test_cancel_after_completion_does_not_change_terminal_status(client):
    experiment = wait_for_run(client, create_run(client, games=1).json()["id"])
    cancelled = client.post(f"/api/experiments/{experiment['id']}/cancel").json()
    assert cancelled["status"] == "completed"
    assert not client.app.state.store.update_status(
        experiment["id"], "running", expected=("queued",)
    )


def test_worker_timeout_is_a_failure_not_a_draw(tmp_path, monkeypatch):
    import subprocess

    from backend.runner import Runner

    def timed_out(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", timed_out)
    runner = Runner(Store(tmp_path))
    try:
        result = runner._match({}, 1)
        assert result["status"] == "failed"
        assert result["winner"] is None
        assert "wall-clock limit" in result["error"]
    finally:
        runner.close()
