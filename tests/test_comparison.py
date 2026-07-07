import pandas as pd

from etl_test.core.comparison import compare
from etl_test.core.normalize import ColumnNormSpec


def _src():
    return pd.DataFrame([
        {"id": "1", "amt": "1,000", "flag": "Public"},
        {"id": "2", "amt": "2000", "flag": "Private"},
        {"id": "3", "amt": "3000", "flag": "Public"},
    ])


def test_clean_match_ignores_formatting_and_case():
    src = _src()
    tgt = pd.DataFrame([
        {"id": "1", "amt": "1000", "flag": "public"},
        {"id": "2", "amt": "2000", "flag": "private"},
        {"id": "3", "amt": "3000", "flag": "PUBLIC"},
    ])
    specs = {"amt": ColumnNormSpec("amt", kind="numeric"),
             "flag": ColumnNormSpec("flag", kind="string")}
    res = compare(src, tgt, ["id"], ["amt", "flag"], specs)
    assert res.is_clean
    assert res.matched == 3
    assert res.value_mismatches == 0


def test_detects_missing_extra_and_mismatch():
    src = _src()
    tgt = pd.DataFrame([
        {"id": "1", "amt": "1000", "flag": "Private"},   # flag mismatch
        {"id": "2", "amt": "2000", "flag": "Private"},
        {"id": "4", "amt": "9999", "flag": "Public"},    # extra (id 3 missing)
    ])
    specs = {"amt": ColumnNormSpec("amt", kind="numeric")}
    res = compare(src, tgt, ["id"], ["amt", "flag"], specs)
    assert res.source_only == 1     # id 3
    assert res.target_only == 1     # id 4
    assert res.value_mismatches == 1  # id 1 flag
    assert res.column_mismatch_counts.get("flag") == 1


def test_duplicate_keys_reported_not_exploded():
    src = pd.DataFrame([{"id": "1", "v": "a"}, {"id": "1", "v": "b"},
                        {"id": "2", "v": "c"}])
    tgt = pd.DataFrame([{"id": "1", "v": "a"}, {"id": "2", "v": "c"}])
    res = compare(src, tgt, ["id"], ["v"], {})
    assert res.source_dup_keys == 1
    # id 1 excluded from 1:1 matching; id 2 matches
    assert res.matched == 1
    assert res.is_clean is False


def test_missing_key_raises():
    src = pd.DataFrame([{"id": "1"}])
    tgt = pd.DataFrame([{"other": "1"}])
    try:
        compare(src, tgt, ["id"], [], {})
        assert False, "expected ValueError"
    except ValueError:
        pass
