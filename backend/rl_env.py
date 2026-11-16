"""A candidate-perspective episode; use one native battle per OS process."""

import copy
import random
import threading

from backend.agents import choose
from backend.engine import engine_identity, load_engine, starter_deck

_BATTLE_LOCK = threading.Lock()


def validate_action(action, observation):
    selection = observation["select"]
    if not isinstance(action, list) or any(type(index) is not int for index in action):
        raise ValueError("Action must be a list of Python integer option indices.")
    if (
        len(set(action)) != len(action)
        or not selection["minCount"] <= len(action) <= selection["maxCount"]
        or any(not 0 <= index < len(selection["option"]) for index in action)
    ):
        raise ValueError("Action violates the current legal selection bounds.")


class CABTEnv:
    """Gym-style tuples without a Gym dependency or fixed-size action space.

    Candidate is player 0. Opponent decisions are automatic and never returned.
    Native RNG cannot be seeded. Always close the environment, preferably with `with`.
    """

    def __init__(self, *, decks=None, opponent="random", max_decisions=2000, reverse=False):
        if opponent not in ("random", "first"):
            raise ValueError("Opponent must be 'random' or 'first'.")
        if type(max_decisions) is not int or max_decisions < 1:
            raise ValueError("max_decisions must be a positive integer.")
        if type(reverse) is not bool:
            raise ValueError("reverse must be a boolean.")
        self.decks = copy.deepcopy(decks if decks is not None else [starter_deck(), starter_deck()])
        if (
            not isinstance(self.decks, list)
            or len(self.decks) != 2
            or any(
                not isinstance(deck, list)
                or len(deck) != 60
                or any(type(card) is not int for card in deck)
                for deck in self.decks
            )
        ):
            raise ValueError("Supply two 60-card lists of integer CABT card IDs.")
        self.opponent = opponent
        self.max_decisions = max_decisions
        self.reverse = reverse
        self._locked = False
        self._owns_battle = False
        self._observation = None
        self._status = "not_started"
        self.decisions = 0

    def reset(self, *, seed=42):
        if type(seed) is not int:
            raise ValueError("seed must be an integer; it seeds policy RNG only.")
        self.close()
        if not _BATTLE_LOCK.acquire(blocking=False):
            raise RuntimeError("CABT already has an active environment; use separate OS processes.")
        self._locked = True
        try:
            self._sim, self._game = load_engine()
            if self._sim.Battle.battle_ptr:
                raise RuntimeError("Another native CABT battle is active in this process.")
            self._sim.Battle.lib = self._sim.get_lib(2)
            self._owns_battle = True
            self._observation, start = self._game.battle_start(*self.decks, self.reverse)
            if self._observation is None or start.errorPlayer >= 0:
                raise ValueError(
                    f"Engine rejected deck for player {start.errorPlayer}: error {start.errorType}"
                )
            self.policy_seed = seed
            self._rng = random.Random(seed + 1)
            self.decisions = 0
            self._status = "running"
            self._advance_opponent()
            return self._candidate_observation(), self._info()
        except BaseException:
            self.close()
            raise

    def _settle(self):
        result = self._observation["current"]["result"]
        if result >= 0:
            self._status = "completed"
        elif self.decisions >= self.max_decisions:
            self._status = "capped"

    def _select(self, action):
        validate_action(action, self._observation)
        self._observation = self._game.battle_select(action)
        self.decisions += 1
        self._settle()

    def _advance_opponent(self):
        self._settle()
        while self._status == "running" and self._observation["current"]["yourIndex"] != 0:
            action, _ = choose(self.opponent, self._observation, self._rng)
            self._select(action)

    def _candidate_observation(self):
        if self._observation["current"]["yourIndex"] != 0:
            return None
        return copy.deepcopy(self._observation)

    def _info(self):
        result = self._observation["current"]["result"]
        return {
            "status": self._status,
            "winner": result if self._status == "completed" and result in (0, 1) else None,
            "decisions": self.decisions,
            "candidate_player": 0,
            "first_player": self._observation["current"]["firstPlayer"],
            "reverse": self.reverse,
            "policy_seed": self.policy_seed,
            "native_rng_seeded": False,
        }

    def step(self, action):
        if self._status != "running" or not self._owns_battle:
            raise RuntimeError("Call reset before stepping; this episode is not running.")
        self._select(action)
        self._advance_opponent()
        info = self._info()
        terminated, truncated = self._status == "completed", self._status == "capped"
        reward = float(terminated and info["winner"] == 0)
        return self._candidate_observation(), reward, terminated, truncated, info

    @property
    def engine(self):
        return engine_identity()

    def close(self):
        try:
            if self._owns_battle and self._sim.Battle.battle_ptr:
                self._game.battle_finish()
                self._sim.Battle.battle_ptr = None
        finally:
            self._owns_battle = False
            if self._locked:
                self._locked = False
                _BATTLE_LOCK.release()
            self._status = "closed"

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
