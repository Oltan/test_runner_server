"""projects.yaml yükleme ve doğrulama."""
from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class ResultsConfig(BaseModel):
    # Koşum sonunda kesin istatistik için okunacak rapor yolları (proje dizinine göre göreli).
    cucumber_json: str | None = None
    junit_xml_dir: str | None = None


class LiveProgressConfig(BaseModel):
    # Cucumber "message" plugin'inin yazdığı NDJSON dosyası; koşum sırasında tail edilir.
    cucumber_ndjson: str | None = None


class ProjectConfig(BaseModel):
    id: str
    name: str
    path: str
    command: str
    env: dict[str, str] = Field(default_factory=dict)
    results: ResultsConfig = Field(default_factory=ResultsConfig)
    live_progress: LiveProgressConfig = Field(default_factory=LiveProgressConfig)


class ServerConfig(BaseModel):
    auth_token: str
    data_dir: str = "data"
    projects: list[ProjectConfig] = Field(default_factory=list)

    def project(self, project_id: str) -> ProjectConfig | None:
        for p in self.projects:
            if p.id == project_id:
                return p
        return None


def load_config(path: str | os.PathLike | None = None) -> ServerConfig:
    cfg_path = Path(path or os.environ.get("CONFIG_PATH", "projects.yaml"))
    with open(cfg_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return ServerConfig(**raw)
