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
from ...compare.store import CompareStore
from ...guide_generation.store import GuideGenerationStore
from .client import FeishuOpenApiClient
from .onboarding import FeishuAppOnboarding
from .runtime import FeishuAppRuntime
from .service import FeishuService


def main() -> int:
    store = RunStore(local_data_dir())
    tasks = TaskStore(store)
    service = FeishuService(
        store, tasks, TaskApplicationService(store, tasks), FeishuOpenApiClient.from_env(),
        compare_store=CompareStore(store),
        guide_store=GuideGenerationStore(store),
    )
    service.install()
    # Users in other Feishu tenants bring their own self-built app; each such
    # app gets a long-connection client and replies are routed by tenant.
    onboarding = FeishuAppOnboarding(store)
    runtime = FeishuAppRuntime(onboarding, service)
    service.set_app_clients(runtime.client_for)
    runtime.start()
    background = threading.Thread(target=service.run_background, name="fundlex-feishu-sync", daemon=True)
    background.start()
    service.client.start()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
