import argparse
import copy
import json
import random
import time
from pathlib import Path

from backend.agents import choose
from backend.engine import engine_identity, load_engine


def run_match(config: dict) -> dict:
    sim, game = load_engine()
    sim.Battle.lib = sim.get_lib(2)
    started = time.monotonic()
    decisions = []
    rngs = [random.Random(config["policy_seed"] + player) for player in range(2)]
    observation = None
    try:
        observation, start = game.battle_start(
            config["decks"][0], config["decks"][1], config["reverse"]
        )
        if observation is None or start.errorPlayer >= 0:
            raise ValueError(
                f"Engine rejected deck for player {start.errorPlayer}: error {start.errorType}"
            )
        for index in range(config["max_decisions"]):
            current = observation["current"]
            if current["result"] >= 0:
                return {
                    "status": "completed",
                    "winner": current["result"] if current["result"] in (0, 1) else None,
                    "decisions": decisions,
                    "final_observation": observation,
                    "duration_ms": round((time.monotonic() - started) * 1000, 2),
                    "engine": engine_identity(),
                }
            player = current["yourIndex"]
            before = time.perf_counter()
            selected, diagnostics = choose(config["agents"][player], observation, rngs[player])
            latency = (time.perf_counter() - before) * 1000
            decisions.append(
                {
                    "index": index,
                    "player": player,
                    "observation": copy.deepcopy(observation),
                    "selected": selected,
                    "latency_ms": round(latency, 4),
                    "diagnostics": diagnostics,
                }
            )
            observation = game.battle_select(selected)
        if observation["current"]["result"] >= 0:
            result = observation["current"]["result"]
            status, winner = "completed", result if result in (0, 1) else None
        else:
            status, winner = "capped", None
        return {
            "status": status,
            "winner": winner,
            "decisions": decisions,
            "final_observation": observation,
            "duration_ms": round((time.monotonic() - started) * 1000, 2),
            "engine": engine_identity(),
        }
    except Exception as error:
        return {
            "status": "failed",
            "winner": None,
            "error": str(error),
            "decisions": decisions,
            "final_observation": observation,
            "duration_ms": round((time.monotonic() - started) * 1000, 2),
        }
    finally:
        if sim.Battle.battle_ptr:
            game.battle_finish()
            sim.Battle.battle_ptr = None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    config = json.loads(args.input.read_text())
    args.output.write_text(json.dumps(run_match(config)))


if __name__ == "__main__":
    main()
