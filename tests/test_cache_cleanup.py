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


def test_trim_evicts_the_oldest_entries_first():
    cache = {f"k{i}": {"timestamp": 1000 + i} for i in range(10)}

    backend_app_module.trim_cache_to_size(cache, 4)

    assert sorted(cache) == ["k6", "k7", "k8", "k9"]


def test_trim_leaves_a_cache_under_the_cap_alone():
    cache = {"a": {"timestamp": 1}, "b": {"timestamp": 2}}

    backend_app_module.trim_cache_to_size(cache, 5)

    assert sorted(cache) == ["a", "b"]


def test_fresh_distinct_keys_cannot_grow_a_cache_past_the_cap(monkeypatch):
    """Every entry here is within TTL, so only the size cap can bound it."""
    now = time.time()
    monkeypatch.setattr(backend_app_module, "CACHE_MAX_ENTRIES", 20)
    for name in ("stop_candidate_cache", "ranked_stops_cache", "geocode_cache", "route_cache"):
        monkeypatch.setattr(
            backend_app_module, name, {f"k{i}": {"timestamp": now - i * 0.001} for i in range(200)}
        )

    backend_app_module.cleanup_stop_candidate_cache(now)
    backend_app_module.cleanup_geocode_cache(now)
    backend_app_module.cleanup_route_cache(now)

    for name in ("stop_candidate_cache", "ranked_stops_cache", "geocode_cache", "route_cache"):
        cache = getattr(backend_app_module, name)
        assert len(cache) == 20, name
        assert "k0" in cache, f"{name} evicted its newest entry"


def test_stale_routes_are_swept(monkeypatch):
    now = 10_000.0
    ttl = backend_app_module.ROUTE_CACHE_TTL_SECONDS
    monkeypatch.setattr(
        backend_app_module,
        "route_cache",
        {"old": {"timestamp": now - ttl - 1}, "new": {"timestamp": now - 1}},
    )

    backend_app_module.cleanup_route_cache(now)

    assert list(backend_app_module.route_cache) == ["new"]
