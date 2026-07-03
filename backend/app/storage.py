import asyncio
import json
from typing import Optional

from app.config import RUNS_DIR
from app.models import TestRun


class RunStore:
    """Keeps test runs in memory, persists them to disk, and fans out
    live events to any websocket subscribers for a given run."""

    def __init__(self) -> None:
        self._runs: dict[str, TestRun] = {}
        self._subscribers: dict[str, list[asyncio.Queue]] = {}

    def create(self, run: TestRun) -> None:
        self._runs[run.id] = run
        self._persist(run)

    def get(self, run_id: str) -> Optional[TestRun]:
        return self._runs.get(run_id)

    def list(self) -> list[TestRun]:
        return sorted(self._runs.values(), key=lambda r: r.started_at, reverse=True)

    def update(self, run: TestRun) -> None:
        self._runs[run.id] = run
        self._persist(run)

    def _persist(self, run: TestRun) -> None:
        path = RUNS_DIR / f"{run.id}.json"
        path.write_text(run.model_dump_json(indent=2), encoding="utf-8")

    def load_from_disk(self) -> None:
        for path in RUNS_DIR.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                run = TestRun.model_validate(data)
                self._runs[run.id] = run
            except Exception:
                continue

    def subscribe(self, run_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers.setdefault(run_id, []).append(queue)
        return queue

    def unsubscribe(self, run_id: str, queue: asyncio.Queue) -> None:
        subs = self._subscribers.get(run_id, [])
        if queue in subs:
            subs.remove(queue)

    async def publish(self, run_id: str, event: dict) -> None:
        for queue in list(self._subscribers.get(run_id, [])):
            await queue.put(event)


store = RunStore()
