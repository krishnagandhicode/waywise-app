import time
from importlib import import_module
from itertools import count

backend_app_module = import_module("backend.app")

find_stale_cache_keys = backend_app_module.find_stale_cache_keys


class ConcurrentWriteValue(dict):
    """A cache value that writes to its own cache while being inspected.

    Stands in for another request thread inserting a cache entry in the middle
    of a cleanup scan. Deterministic where a real thread race is not.
    """

    def __init__(self, cache, counter, timestamp):
        super().__init__(timestamp=timestamp)
        self._cache = cache
        self._counter = counter

    def get(self, key, default=None):
        self._cache[f"injected-{next(self._counter)}"] = {"timestamp": time.time()}
        return super().get(key, default)


def test_returns_only_keys_past_their_ttl():
    now = 1000.0
    cache = {
        "fresh": {"timestamp": now - 10},
        "stale": {"timestamp": now - 500},
        "exactly_at_ttl": {"timestamp": now - 100},
    }
    assert find_stale_cache_keys(cache, 100, now) == ["stale"]


def test_missing_timestamp_counts_as_stale():
    assert find_stale_cache_keys({"no_ts": {}}, 100, 1000.0) == ["no_ts"]


def test_empty_cache_is_handled():
    assert find_stale_cache_keys({}, 100, 1000.0) == []


def test_survives_a_write_during_the_scan():
    """Without a snapshot this raises RuntimeError: dictionary keys changed
    during iteration, which is how the cleanup helpers failed under threads."""
    counter = count()
    cache = {}
    for i in range(25):
        cache[f"key-{i}"] = ConcurrentWriteValue(cache, counter, timestamp=0)

    stale = find_stale_cache_keys(cache, 100, 1000.0)

    assert len(stale) == 25
    assert all(key.startswith("key-") for key in stale)


def test_cleanup_entry_points_evict_expired_entries(monkeypatch):
    monkeypatch.setattr(backend_app_module, "stop_candidate_cache", {})
    monkeypatch.setattr(backend_app_module, "ranked_stops_cache", {})
    monkeypatch.setattr(backend_app_module, "geocode_cache", {})

    now = time.time()
    backend_app_module.stop_candidate_cache["old"] = {"timestamp": now - 10_000}
    backend_app_module.stop_candidate_cache["new"] = {"timestamp": now}
    backend_app_module.ranked_stops_cache["old"] = {"timestamp": now - 10_000}
    backend_app_module.ranked_stops_cache["new"] = {"timestamp": now}
    backend_app_module.geocode_cache["old"] = {"timestamp": now - 10_000}
    backend_app_module.geocode_cache["new"] = {"timestamp": now}

    backend_app_module.cleanup_stop_candidate_cache()
    backend_app_module.cleanup_geocode_cache()

    assert list(backend_app_module.stop_candidate_cache) == ["new"]
    assert list(backend_app_module.ranked_stops_cache) == ["new"]
    assert list(backend_app_module.geocode_cache) == ["new"]
