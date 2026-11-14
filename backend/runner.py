import json
import logging
import subprocess
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from backend.store import Store

ROOT = Path(__file__).resolve().parents[1]
logger = logging.getLogger(__name__)


class Runner:
    def __init__(self, store: Store):
        self.store = store
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="experiment")
        self.stopping = threading.Event()
        for experiment in store.experiments():
            if experiment["status"] in ("running", "queued", "cancelling"):
                store.update_status(
                    experiment["id"], "interrupted", "Studio stopped before this run finished."
                )

    def submit(self, experiment_id):
        self.executor.submit(self._run, experiment_id)

    def close(self):
        self.stopping.set()
        self.executor.shutdown(wait=True, cancel_futures=True)

    def _run(self, experiment_id):
        try:
            experiment = self.store.experiment(experiment_id)
            if self.stopping.is_set():
                return
            if not self.store.update_status(experiment_id, "running", expected=("queued",)):
                return
            config = experiment["config"]
            for number in range(config["games"]):
                if self.stopping.is_set():
                    self.store.update_status(experiment_id, "interrupted")
                    return
                if self.store.experiment(experiment_id)["status"] in ("cancelled", "cancelling"):
                    self.store.update_status(experiment_id, "cancelled")
                    return
                protocol = {
                    "agents": config["agent_ids"],
                    "decks": [deck["cards"] for deck in experiment["decks"]],
                    "reverse": bool(number % 2),
                    "policy_seed": config["policy_seed"] + number * 2,
                    "max_decisions": config["max_decisions"],
                }
                result = self._match(protocol, config["timeout_seconds"])
                self.store.save_game(experiment_id, number + 1, result, protocol)
            if not self.store.update_status(experiment_id, "completed", expected=("running",)):
                self.store.update_status(experiment_id, "cancelled", expected=("cancelling",))
        except Exception:
            logger.exception("Experiment %s failed", experiment_id)
            self.store.update_status(
                experiment_id, "failed", "Experiment worker failed; see server log."
            )

    def _match(self, protocol, timeout):
        with tempfile.TemporaryDirectory(prefix="tcg-match-") as directory:
            input_path = Path(directory) / "input.json"
            output_path = Path(directory) / "output.json"
            input_path.write_text(json.dumps(protocol))
            try:
                process = subprocess.run(
                    [sys.executable, "-m", "backend.worker", str(input_path), str(output_path)],
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    check=False,
                )
                if process.returncode:
                    return {
                        "status": "failed",
                        "winner": None,
                        "error": f"Native worker exited with code {process.returncode}. "
                        + process.stderr[-1000:],
                        "decisions": [],
                        "duration_ms": 0,
                    }
                return json.loads(output_path.read_text())
            except subprocess.TimeoutExpired:
                return {
                    "status": "failed",
                    "winner": None,
                    "error": f"Match exceeded the {timeout}s wall-clock limit.",
                    "decisions": [],
                    "duration_ms": timeout * 1000,
                }
