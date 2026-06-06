from __future__ import annotations


def test_put_then_get_roundtrips(tmp_path) -> None:
    from prescient.edge.data.cache import JsonFileCache

    cache = JsonFileCache(tmp_path)
    assert cache.get("earnings:MU:2024") is None
    cache.put("earnings:MU:2024", {"rows": [1, 2, 3]})
    assert cache.get("earnings:MU:2024") == {"rows": [1, 2, 3]}


def test_keys_with_unsafe_chars_are_isolated(tmp_path) -> None:
    from prescient.edge.data.cache import JsonFileCache

    cache = JsonFileCache(tmp_path)
    cache.put("a/b:c d", {"x": 1})
    cache.put("a_b_c_d_other", {"x": 2})
    assert cache.get("a/b:c d") == {"x": 1}


def test_corrupt_file_returns_none(tmp_path) -> None:
    from prescient.edge.data.cache import JsonFileCache

    cache = JsonFileCache(tmp_path)
    cache.put("k", {"x": 1})
    for p in tmp_path.iterdir():
        p.write_text("not json", encoding="utf-8")
    assert cache.get("k") is None
