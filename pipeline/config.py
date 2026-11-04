"""Load config.yaml into an attribute-accessible dict."""
from __future__ import annotations

from pathlib import Path

import yaml


class Cfg(dict):
    """dict with attribute access, recursively."""

    def __getattr__(self, k):
        try:
            v = self[k]
        except KeyError as e:
            raise AttributeError(k) from e
        return Cfg(v) if isinstance(v, dict) else v


def load_config(path: str | Path | None = None) -> Cfg:
    path = Path(path) if path else Path(__file__).resolve().parent.parent / "config.yaml"
    with open(path, "r", encoding="utf-8") as f:
        return Cfg(yaml.safe_load(f) or {})
