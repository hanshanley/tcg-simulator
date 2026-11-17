import importlib.abc
import importlib.machinery
import importlib.util
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

from backend import engine


def test_concurrent_cold_engine_load_initializes_native_wrapper_once(monkeypatch):
    spec = importlib.util.spec_from_file_location("_cold_engine", engine.__file__)
    cold_engine = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cold_engine)
    initializations = []
    start = threading.Barrier(8, timeout=5)

    class Loader(importlib.abc.Loader):
        def create_module(self, spec):
            return None

        def exec_module(self, module):
            if module.__name__.endswith(".sim"):
                initializations.append(module)
                time.sleep(0.05)

    for name in ("_studio_cabt", "_studio_cabt.sim", "_studio_cabt.game"):
        monkeypatch.setitem(sys.modules, name, None)
    monkeypatch.setattr(
        importlib.metadata,
        "distribution",
        lambda name: SimpleNamespace(locate_file=lambda path: Path.cwd()),
    )
    monkeypatch.setattr(
        importlib.util,
        "spec_from_file_location",
        lambda name, path: importlib.machinery.ModuleSpec(name, Loader()),
    )

    def load(_):
        start.wait()
        return cold_engine.load_engine()

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(load, range(8)))
    assert len(initializations) == 1
    assert all(result[0] is results[0][0] and result[1] is results[0][1] for result in results)
