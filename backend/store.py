import gzip
import hashlib
import json
import math
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from backend.engine import starter_deck


def now():
    return datetime.now(UTC).isoformat()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def summarize(games):
    completed = [game for game in games if game["status"] == "completed"]
    wins = sum(game["winner"] == 0 for game in completed)
    losses = sum(game["winner"] == 1 for game in completed)
    draws = len(completed) - wins - losses
    n = len(completed)
    interval = None
    if n:
        p, z = wins / n, 1.959963984540054
        divisor = 1 + z * z / n
        center = (p + z * z / (2 * n)) / divisor
        margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / divisor
        interval = [max(0, center - margin), min(1, center + margin)]
    return {
        "wins": wins,
        "losses": losses,
        "draws": draws,
        "completed": n,
        "failed": sum(game["status"] == "failed" for game in games),
        "capped": sum(game["status"] == "capped" for game in games),
        "win_rate": wins / n if n else None,
        "win_rate_ci": interval,
        "decisions": sum(game.get("decision_count", 0) for game in games),
        "duration_ms": round(sum(game.get("duration_ms", 0) for game in games), 2),
    }


class Store:
    def __init__(self, directory: Path):
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)
        (directory / "replays").mkdir(exist_ok=True)
        with self.connection() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS decks (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS experiments (
                    id TEXT PRIMARY KEY, payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS games (
                    id TEXT PRIMARY KEY, experiment_id TEXT NOT NULL, payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS games_experiment ON games(experiment_id);
                CREATE TABLE IF NOT EXISTS bookmarks (
                    game_id TEXT NOT NULL, decision INTEGER NOT NULL, label TEXT NOT NULL,
                    PRIMARY KEY (game_id, decision)
                );
            """)
        if not self.decks():
            self.add_deck("CABT starter", starter_deck(), "Official environment's example deck.")

    @contextmanager
    def connection(self):
        connection = sqlite3.connect(self.directory / "studio.sqlite3", timeout=10)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def decks(self):
        with self.connection() as db:
            rows = db.execute("SELECT payload FROM decks ORDER BY rowid DESC").fetchall()
        return [json.loads(row[0]) for row in rows]

    def add_deck(self, name, cards, description=""):
        deck = {
            "id": uuid.uuid4().hex,
            "name": name,
            "description": description,
            "cards": cards,
            "sha256": digest(sorted(cards)),
            "created_at": now(),
        }
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute("SELECT payload FROM decks").fetchall()
            deck["version"] = 1 + sum(json.loads(row[0])["name"] == name for row in rows)
            db.execute("INSERT INTO decks VALUES (?, ?)", (deck["id"], json.dumps(deck)))
        return deck

    def deck(self, deck_id):
        return next((deck for deck in self.decks() if deck["id"] == deck_id), None)

    def create_experiment(self, config, engine, agents):
        experiment = {
            "id": uuid.uuid4().hex,
            "name": config["name"],
            "status": "queued",
            "created_at": now(),
            "updated_at": now(),
            "config": config,
            "engine": engine,
            "agents": agents,
            "decks": [self.deck(deck_id) for deck_id in config["deck_ids"]],
        }
        with self.connection() as db:
            db.execute(
                "INSERT INTO experiments VALUES (?, ?)",
                (experiment["id"], json.dumps(experiment)),
            )
        return self.experiment(experiment["id"])

    def experiments(self):
        with self.connection() as db:
            rows = db.execute("SELECT payload FROM experiments ORDER BY rowid DESC").fetchall()
        return [self._with_results(json.loads(row[0])) for row in rows]

    def experiment(self, experiment_id):
        with self.connection() as db:
            row = db.execute(
                "SELECT payload FROM experiments WHERE id = ?", (experiment_id,)
            ).fetchone()
        return self._with_results(json.loads(row[0])) if row else None

    def _with_results(self, experiment):
        games = self.games(experiment["id"])
        experiment["games"] = games
        experiment["summary"] = summarize(games)
        return experiment

    def update_status(self, experiment_id, status, error=None, expected=None):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT payload FROM experiments WHERE id = ?", (experiment_id,)
            ).fetchone()
            payload = json.loads(row[0])
            if expected is not None and payload["status"] not in expected:
                return False
            payload.update(status=status, updated_at=now())
            if error:
                payload["error"] = error
            db.execute(
                "UPDATE experiments SET payload = ? WHERE id = ?",
                (json.dumps(payload), experiment_id),
            )
        return True

    def games(self, experiment_id):
        with self.connection() as db:
            rows = db.execute(
                "SELECT payload FROM games WHERE experiment_id = ? ORDER BY rowid",
                (experiment_id,),
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def save_game(self, experiment_id, number, result, protocol):
        game_id = uuid.uuid4().hex
        result.update(id=game_id, experiment_id=experiment_id, number=number, protocol=protocol)
        path = self.directory / "replays" / f"{game_id}.json.gz"
        with gzip.open(path.with_suffix(".tmp"), "wt", encoding="utf-8") as file:
            json.dump(result, file)
        path.with_suffix(".tmp").replace(path)
        latencies = sorted(decision["latency_ms"] for decision in result["decisions"])
        summary = {
            key: value
            for key, value in result.items()
            if key not in ("decisions", "final_observation", "engine")
        }
        summary["decision_count"] = len(result["decisions"])
        summary["p95_latency_ms"] = (
            latencies[max(0, math.ceil(len(latencies) * 0.95) - 1)] if latencies else None
        )
        final = result.get("final_observation")
        summary["turns"] = final["current"]["turn"] if final else 0
        summary["first_player"] = final["current"]["firstPlayer"] if final else -1
        with self.connection() as db:
            db.execute(
                "INSERT INTO games VALUES (?, ?, ?)",
                (game_id, experiment_id, json.dumps(summary)),
            )
        return summary

    def replay(self, game_id):
        with self.connection() as db:
            row = db.execute("SELECT id FROM games WHERE id = ?", (game_id,)).fetchone()
        if not row:
            return None
        with gzip.open(self.directory / "replays" / f"{game_id}.json.gz", "rt") as file:
            replay = json.load(file)
        with self.connection() as db:
            bookmarks = db.execute(
                "SELECT decision, label FROM bookmarks WHERE game_id = ?", (game_id,)
            ).fetchall()
        replay["bookmarks"] = [
            {"decision": decision, "label": label} for decision, label in bookmarks
        ]
        return replay

    def bookmark(self, game_id, decision, label):
        with self.connection() as db:
            if label:
                db.execute(
                    "INSERT OR REPLACE INTO bookmarks VALUES (?, ?, ?)",
                    (game_id, decision, label),
                )
            else:
                db.execute(
                    "DELETE FROM bookmarks WHERE game_id = ? AND decision = ?",
                    (game_id, decision),
                )
