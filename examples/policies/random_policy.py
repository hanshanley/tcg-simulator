"""Self-contained baseline for the Harbor policy-file contract."""


def select(observation, rng):
    selection = observation["select"]
    maximum = min(selection["maxCount"], len(selection["option"]))
    count = rng.randint(selection["minCount"], maximum)
    return rng.sample(range(len(selection["option"])), count)
