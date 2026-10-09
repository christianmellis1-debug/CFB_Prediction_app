"""Bounded caching for pure calculations; all inputs and source revisions matter."""
from functools import wraps
from hashlib import sha256
import pickle

import pandas as pd
import streamlit as st


def frame_digest(frame):
    # Hash every row, dtype, index and attribute, including large uploaded frames.
    # Streamlit's default large-frame hashing samples rows.
    return sha256(pickle.dumps(frame, protocol=5)).hexdigest()


@st.cache_data(ttl=3600, max_entries=64, show_spinner=False,
               hash_funcs={pd.DataFrame: frame_digest, pd.Series: frame_digest})
def _calculate(_function, identity, revision, args, kwargs):
    return _function(*args, **kwargs)


def cache_calculation(revision):
    """Cache a pure function, returning isolated copies and preserving its API."""
    def decorate(function):
        identity = function.__module__ + "." + function.__qualname__

        @wraps(function)
        def cached(*args, **kwargs):
            return _calculate(function, identity, revision, args, kwargs)

        return cached
    return decorate


def clear_calculations():
    _calculate.clear()
