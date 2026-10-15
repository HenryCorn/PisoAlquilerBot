from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True, slots=True)
class Settings:
    raw: dict[str, Any]

    @property
    def search(self) -> dict[str, Any]:
        return self.raw["search"]

    @property
    def portals(self) -> dict[str, Any]:
        return self.raw["portals"]

    @property
    def runtime(self) -> dict[str, Any]:
        return self.raw["runtime"]


def load_settings(path: str | Path = "config.yaml") -> Settings:
    with Path(path).open(encoding="utf-8") as config_file:
        data = yaml.safe_load(config_file)
    for section in ("search", "portals", "runtime"):
        if not isinstance(data.get(section), dict):
            raise ValueError(f"Missing config section: {section}")
    if database_path := os.getenv("PISORENT_DATABASE_PATH"):
        data["runtime"]["database_path"] = database_path
    return Settings(data)
