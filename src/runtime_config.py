"""
Runtime mutable configuration — survives without server restart.
Initialized from environment variables, overridable via admin panel.
"""
import os

_state = {
    "use_case_id": os.environ.get("USE_CASE_ID", "robles_ai"),
    "forward_to":  os.environ.get("FORWARD_TO", ""),
}


def get(key, default=None):
    return _state.get(key, default)


def set(key, value):
    _state[key] = value


def all_config():
    return dict(_state)
