import hashlib
import inspect
import random


def choose(agent: str, observation: dict, rng: random.Random) -> tuple[list[int], dict]:
    selection = observation["select"]
    options = selection["option"]
    minimum = selection["minCount"]
    maximum = min(selection["maxCount"], len(options))
    if not 0 <= minimum <= maximum:
        raise ValueError(f"Invalid selection bounds: {minimum}..{maximum}")
    if agent == "random":
        count = rng.randint(minimum, maximum)
        selected = rng.sample(range(len(options)), count)
        diagnostics = {"policy": "Uniform legal subset", "selected_count": count}
    elif agent == "first":
        selected = list(range(maximum))
        diagnostics = {"policy": "First legal choices", "selected_count": maximum}
    else:
        raise ValueError(f"Unknown agent: {agent}")
    return selected, diagnostics


def agent_catalog():
    source = inspect.getsource(choose)
    return [
        {
            "id": agent,
            "name": name,
            "version": "1",
            "description": description,
            "artifact_sha256": hashlib.sha256(f"{agent}\n{source}".encode()).hexdigest(),
        }
        for agent, name, description in [
            ("random", "Random baseline", "Samples a legal subset within the selection bounds."),
            (
                "first",
                "First-choice baseline",
                "Selects the first available options, up to maxCount.",
            ),
        ]
    ]
