"""Panel bildirim kuralları; kamera/model ayarlarını değiştirmez."""
from __future__ import annotations

import contextlib
import json
import os
import threading
import uuid
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class PanelRule(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    camera_id: str = Field(min_length=1, max_length=200)
    kind: Literal["intrusion", "plate", "face", "fire", "telefon", "sigara"]
    enabled: bool = True
    popup: bool = True
    sound: bool = False
    tone: Literal["soft", "urgent"] = "soft"
    cooldown: int = Field(default=60, ge=0, le=3600)


class RuleSet(BaseModel):
    revision: int = Field(default=0, ge=0)
    rules: list[PanelRule] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def unique_ids(self):
        if len({rule.id for rule in self.rules}) != len(self.rules):
            raise ValueError("Duplicate rule IDs")
        return self


@contextlib.contextmanager
def _dosya_kilidi(path: Path):
    """Süreçler arası kilit: birden çok uvicorn işçisi aynı revizyonu okuyup
    ikisi de yazamasın. fcntl olmayan platformda (Windows) süreç içi kilide düşer."""
    try:
        import fcntl
    except ImportError:
        yield
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path.with_name(path.name + '.lock'), 'a+') as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


class RuleRepository:
    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.RLock()

    def load(self):
        with self.lock:
            if not self.path.exists():
                return RuleSet().model_dump()
            return RuleSet.model_validate_json(
                self.path.read_text(encoding="utf-8")
            ).model_dump()

    def save(self, payload: RuleSet):
        with self.lock, _dosya_kilidi(self.path):
            current = self.load()
            if current["revision"] != payload.revision:
                raise ValueError("Rules changed; refresh before saving")
            data = payload.model_dump()
            data["revision"] += 1
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp = self.path.with_name(self.path.name + "." + uuid.uuid4().hex + ".tmp")
            try:
                temp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
                os.replace(temp, self.path)
            finally:
                temp.unlink(missing_ok=True)
            return data
