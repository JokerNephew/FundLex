"""Long-running Feishu service entrypoint.

The WebSocket client is blocking by design; it runs in this dedicated process
alongside a small status/outbox thread and never inside FastAPI's event loop.
"""
from __future__ import annotations

import threading

from ...config import local_data_dir
from ...store import RunStore
from ...tasks import TaskStore
from ...application import TaskApplicationService
from .client import FeishuOpenApiClient
from .service import FeishuService


def main() -> int:
    from ... import guide_store
    store = RunStore(local_data_dir())
    tasks = TaskStore(store)
    service = FeishuService(store, tasks, TaskApplicationService(store, tasks), FeishuOpenApiClient.from_env())
    service.install()
    background = threading.Thread(target=service.run_background, name="fundlex-feishu-sync", daemon=True)
    background.start()
    service.client.start()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
