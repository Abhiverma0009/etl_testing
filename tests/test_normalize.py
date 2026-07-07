import numpy as np
import pandas as pd

from etl_test.core.normalize import (
    ColumnNormSpec, NULL, coerce_numeric, is_nullish, normalize_series, values_equal,
)


def test_is_nullish_distinguishes_zero_from_null():
    assert is_nullish(None)
    assert is_nullish("")
    assert is_nullish("NULL")
    assert is_nullish(np.nan)
    assert not is_nullish(0)
    assert not is_nullish("0")
    assert not is_nullish("abc")


def test_blank_not_null_when_disabled():
    assert not is_nullish("", treat_blank_as_null=False)


def test_coerce_numeric_strips_commas_and_currency():
    s = pd.Series(["1,250,000.00", "$3,000", "", "abc", "0"])
    out = coerce_numeric(s)
    assert out[0] == 1250000.0
    assert out[1] == 3000.0
    assert np.isnan(out[2])   # blank -> NaN
    assert np.isnan(out[3])   # non-numeric -> NaN
    assert out[4] == 0.0


def test_string_normalization_case_and_trim():
    spec = ColumnNormSpec(name="x", kind="string")
    out = normalize_series(pd.Series([" Public ", "PUBLIC", None]), spec)
    assert out[0] == out[1] == "public"
    assert out[2] == NULL


def test_numeric_normalization_keeps_null_distinct_from_zero():
    spec = ColumnNormSpec(name="fmv", kind="numeric")
    out = normalize_series(pd.Series(["1,000", "", "0"]), spec)
    assert out[0] == 1000.0
    assert out[1] == NULL     # null stays null
    assert out[2] == 0.0      # zero stays zero, not null


def test_values_equal_tolerance():
    spec = ColumnNormSpec(name="x", numeric_tolerance=0.5)
    assert values_equal(10.0, 10.4, spec)
    assert not values_equal(10.0, 11.0, spec)


def test_values_equal_null_semantics():
    spec = ColumnNormSpec(name="x")
    assert values_equal(NULL, NULL, spec)
    assert not values_equal(NULL, 0, spec)
