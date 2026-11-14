import ctypes
import hashlib
import importlib.metadata
import importlib.util
import json
import platform
import sys
import types
from functools import lru_cache
from pathlib import Path

ENGINE_VERSION = "1.33.3"
ADAPTER_VERSION = "1"


@lru_cache
def load_engine():
    distribution = importlib.metadata.distribution("kaggle-environments")
    root = Path(distribution.locate_file("kaggle_environments/envs/cabt/cg"))
    package_name = "_studio_cabt"
    package = types.ModuleType(package_name)
    package.__path__ = [str(root)]
    sys.modules[package_name] = package
    for name in ("sim", "game"):
        spec = importlib.util.spec_from_file_location(f"{package_name}.{name}", root / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
    return sys.modules[f"{package_name}.sim"], sys.modules[f"{package_name}.game"]


def engine_identity():
    sim, _ = load_engine()
    path = Path(sim.lib._name)
    return {
        "name": "CABT",
        "package_version": importlib.metadata.version("kaggle-environments"),
        "rules_version": 2,
        "adapter_version": ADAPTER_VERSION,
        "native_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "platform": f"{platform.system()} {platform.machine()}",
        "deterministic_reruns": False,
    }


@lru_cache
def card_catalog():
    sim, _ = load_engine()
    result = {}
    for symbol, key in (("AllCard", "cards"), ("AllAttack", "attacks")):
        function = getattr(sim.lib, symbol)
        function.restype = ctypes.c_char_p
        function.argtypes = []
        result[key] = json.loads(function())
    return result


def starter_deck():
    return (
        [721] * 2
        + [722] * 4
        + [723] * 4
        + [1092]
        + [1121] * 2
        + [1145] * 2
        + [1163] * 2
        + [1219] * 4
        + [1227] * 4
        + [1262] * 2
        + [3] * 33
    )
