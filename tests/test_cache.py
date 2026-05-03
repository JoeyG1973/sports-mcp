from sports_mcp.cache import TTLCache


def test_set_and_get_round_trip():
    cache = TTLCache(clock=lambda: 0.0)
    cache.set("k", "v", ttl_seconds=10)
    assert cache.get("k") == "v"


def test_get_missing_returns_none():
    cache = TTLCache(clock=lambda: 0.0)
    assert cache.get("missing") is None


def test_value_expires_after_ttl():
    now = [0.0]
    cache = TTLCache(clock=lambda: now[0])
    cache.set("k", "v", ttl_seconds=10)
    now[0] = 9.999
    assert cache.get("k") == "v"
    now[0] = 10.0
    assert cache.get("k") is None


def test_keys_isolated():
    cache = TTLCache(clock=lambda: 0.0)
    cache.set("a", 1, ttl_seconds=10)
    cache.set("b", 2, ttl_seconds=10)
    assert cache.get("a") == 1
    assert cache.get("b") == 2


def test_set_overwrites_existing():
    now = [0.0]
    cache = TTLCache(clock=lambda: now[0])
    cache.set("k", "v1", ttl_seconds=10)
    now[0] = 5.0
    cache.set("k", "v2", ttl_seconds=10)
    now[0] = 14.999
    assert cache.get("k") == "v2"
