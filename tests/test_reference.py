"""Reference data, drift guards between generator and pipeline, and small helpers."""
import math

import numpy as np
import pandas as pd

from generator import config as gen_cfg
from pipeline import reference as ref
from pipeline.run_silver import _py


def test_every_canonical_city_maps_to_itself():
    for city in ref.CITY_ALIASES:
        assert ref.CITY_LOOKUP[city.lower()] == city


def test_every_generator_alias_is_known_to_the_pipeline():
    """The pipeline's mapping is maintained separately; this guards against the two drifting apart."""
    for city, aliases in gen_cfg.CITY_ALIASES.items():
        for alias in aliases:
            assert ref.CITY_LOOKUP.get(alias.strip().lower()) == city, alias


def test_generator_and_pipeline_agree_on_cities_statuses_and_vehicles():
    assert set(gen_cfg.CITIES) == set(ref.CITY_ALIASES)
    assert ref.VALID_STATUSES == set(gen_cfg.STATUS_WEIGHTS)
    assert ref.VALID_VEHICLE_TYPES == set(gen_cfg.VEHICLES)


def test_py_converts_missing_values_to_none():
    for missing in (None, math.nan, np.nan, pd.NA, pd.NaT):
        assert _py(missing) is None


def test_py_converts_numpy_and_pandas_scalars_to_plain_python():
    assert type(_py(np.int64(5))) is int
    assert type(_py(np.float64(1.5))) is float
    converted = _py(pd.Timestamp("2026-10-25 10:00:00"))
    assert converted.year == 2026
    assert not isinstance(converted, pd.Timestamp)