import os
from collections import Counter
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, StrictInt, StringConstraints

from backend.agents import agent_catalog
from backend.engine import card_catalog, engine_identity
from backend.runner import ROOT, Runner
from backend.store import Store

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
AgentID = Literal["random", "first"]


class DeckInput(BaseModel):
    name: Name
    cards: list[StrictInt] = Field(min_length=60, max_length=60)
    description: str = Field(default="", max_length=500)


class ExperimentInput(BaseModel):
    name: Name
    agent_ids: tuple[AgentID, AgentID] = ("random", "first")
    deck_ids: tuple[str, str]
    games: int = Field(default=10, ge=1, le=200)
    policy_seed: int = Field(default=42, ge=0, le=2**31 - 1)
    max_decisions: int = Field(default=2500, ge=1, le=10000)
    timeout_seconds: int = Field(default=30, ge=1, le=120)


class BookmarkInput(BaseModel):
    label: str = Field(max_length=200)


def validate_deck(cards):
    catalog = {card["cardId"]: card for card in card_catalog()["cards"]}
    unknown = sorted(set(cards) - catalog.keys())
    if unknown:
        raise HTTPException(422, f"Unknown CABT card IDs: {unknown}")
    counts = Counter(catalog[card]["name"] for card in cards if catalog[card]["cardType"] != 5)
    if any(count > 4 for count in counts.values()):
        raise HTTPException(
            422, "A deck may contain at most four copies of a non-basic-energy name."
        )
    if not any(catalog[card]["basic"] for card in cards):
        raise HTTPException(422, "A deck needs at least one Basic Pokemon.")
    if sum(catalog[card]["aceSpec"] for card in cards) > 1:
        raise HTTPException(422, "A deck may contain at most one ACE SPEC card.")


def create_app(data_dir: Path | None = None):
    @asynccontextmanager
    async def lifespan(app):
        app.state.store = Store(data_dir or Path(os.environ.get("TCG_DATA_DIR", ROOT / "data")))
        app.state.engine = engine_identity()
        app.state.runner = Runner(app.state.store)
        yield
        app.state.runner.close()

    app = FastAPI(title="TCG Research Studio", version="0.1.0", lifespan=lifespan)

    @app.get("/api/health")
    def health():
        return {"status": "ok", "engine": app.state.engine}

    @app.get("/api/catalog")
    def catalog():
        return {**card_catalog(), "agents": agent_catalog(), "engine": app.state.engine}

    @app.get("/api/decks")
    def decks():
        return app.state.store.decks()

    @app.post("/api/decks", status_code=201)
    def add_deck(body: DeckInput):
        validate_deck(body.cards)
        return app.state.store.add_deck(body.name, body.cards, body.description)

    @app.get("/api/experiments")
    def experiments():
        return app.state.store.experiments()

    def get_experiment(experiment_id):
        result = app.state.store.experiment(experiment_id)
        if not result:
            raise HTTPException(404, "Experiment not found")
        return result

    @app.post("/api/experiments", status_code=201)
    def create_experiment(body: ExperimentInput):
        for deck_id in body.deck_ids:
            if not app.state.store.deck(deck_id):
                raise HTTPException(422, "Deck not found")
        agents = {agent["id"]: agent for agent in agent_catalog()}
        experiment = app.state.store.create_experiment(
            body.model_dump(mode="json"),
            app.state.engine,
            [agents[agent] for agent in body.agent_ids],
        )
        app.state.runner.submit(experiment["id"])
        return experiment

    @app.get("/api/experiments/{experiment_id}")
    def experiment(experiment_id: str):
        return get_experiment(experiment_id)

    @app.post("/api/experiments/{experiment_id}/cancel")
    def cancel(experiment_id: str):
        get_experiment(experiment_id)
        if not app.state.store.update_status(experiment_id, "cancelled", expected=("queued",)):
            app.state.store.update_status(experiment_id, "cancelling", expected=("running",))
        return get_experiment(experiment_id)

    @app.get("/api/games/{game_id}")
    def replay(game_id: str):
        result = app.state.store.replay(game_id)
        if result is None:
            raise HTTPException(404, "Replay not found")
        return result

    @app.put("/api/games/{game_id}/bookmarks/{decision}")
    def bookmark(game_id: str, decision: int, body: BookmarkInput):
        result = replay(game_id)
        if not 0 <= decision < len(result["decisions"]):
            raise HTTPException(422, "Decision index out of bounds")
        app.state.store.bookmark(game_id, decision, body.label.strip())
        return {"saved": True}

    dist = ROOT / "dist"
    if dist.exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/")
        def index():
            return FileResponse(dist / "index.html")

    return app


app = create_app()
