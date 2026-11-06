import threading
import time
from types import SimpleNamespace

from rag import service


class FakeQdrant:
    def __init__(self):
        self.calls = 0
        self.lock = threading.Lock()

    def get_collections(self):
        with self.lock:
            self.calls += 1
        time.sleep(0.02)
        return SimpleNamespace(collections=[SimpleNamespace(name="axion-test")])

    def create_collection(self, **kwargs):
        raise AssertionError("No debe crear una colección que ya existe")


def test_collection_readiness_check_is_cached_across_concurrent_requests(monkeypatch):
    fake = FakeQdrant()
    monkeypatch.setattr(service, "client", fake)
    monkeypatch.setattr(service.settings, "qdrant_collection", "axion-test")
    monkeypatch.setattr(service, "_collection_checked_at", 0.0)
    monkeypatch.setattr(service.time, "monotonic", lambda: 100.0)

    threads = [threading.Thread(target=service.ensure_collection) for _ in range(12)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=2)
        assert not thread.is_alive()

    assert fake.calls == 1


def test_collection_readiness_check_revalidates_after_interval(monkeypatch):
    fake = FakeQdrant()
    monkeypatch.setattr(service, "client", fake)
    monkeypatch.setattr(service.settings, "qdrant_collection", "axion-test")
    monkeypatch.setattr(service, "_collection_checked_at", 0.0)

    clock = [100.0]
    monkeypatch.setattr(service.time, "monotonic", lambda: clock[0])
    service.ensure_collection()
    assert fake.calls == 1

    clock[0] += service._COLLECTION_CHECK_INTERVAL_SECONDS - 1
    service.ensure_collection()
    assert fake.calls == 1

    clock[0] += 2
    service.ensure_collection()
    assert fake.calls == 2
