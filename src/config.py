"""config.yaml yükleyici — tüm eşik/parametreler tek yerden (manifest convention)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_CONFIG = _ROOT / "config.yaml"


class Config:
    """config.yaml üzerine ince bir sarmalayıcı; nokta yoluyla erişim sağlar."""

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    def get(self, dotted: str, default: Any = None) -> Any:
        """'detect.conf' gibi noktalı anahtarla değer döndürür."""
        node: Any = self._data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    @property
    def root(self) -> Path:
        return _ROOT


def load_config(path: str | Path | None = None) -> Config:
    """config.yaml'i yükler. Yoksa boş config döner (varsayılanlar kodda)."""
    cfg_path = Path(path) if path else _DEFAULT_CONFIG
    if not cfg_path.exists():
        return Config({})
    with open(cfg_path, "r", encoding="utf-8") as f:
        return Config(yaml.safe_load(f) or {})
