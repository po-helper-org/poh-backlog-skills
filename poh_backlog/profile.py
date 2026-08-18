"""Загрузка и слияние порогов: дефолты, затем доменный профиль."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class ProfileError(Exception):
    """Битый профиль, неизвестный ключ или обращение к несуществующему пути."""


@dataclass(frozen=True)
class Profile:
    values: dict[str, Any]

    def get(self, path: str) -> Any:
        node: Any = self.values
        for part in path.split("."):
            if not isinstance(node, dict) or part not in node:
                raise ProfileError(f"Порог не найден: {path}")
            node = node[part]
        return node


def _merge(defaults: dict, override: dict, prefix: str = "") -> dict:
    merged = dict(defaults)
    for key, value in override.items():
        path = f"{prefix}{key}"
        if key not in defaults:
            raise ProfileError(f"Неизвестный ключ профиля: {path}")
        if isinstance(defaults[key], dict) and isinstance(value, dict):
            merged[key] = _merge(defaults[key], value, prefix=f"{path}.")
        else:
            merged[key] = value
    return merged


def load_profile(defaults_path: Path, profile_path: Path | None = None) -> Profile:
    defaults = yaml.safe_load(Path(defaults_path).read_text(encoding="utf-8")) or {}
    if profile_path is None:
        return Profile(defaults)
    raw = yaml.safe_load(Path(profile_path).read_text(encoding="utf-8")) or {}
    override = {k: v for k, v in raw.items() if k != "mapping"}
    return Profile(_merge(defaults, override))
