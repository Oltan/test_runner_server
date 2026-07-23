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
    # FailureArtifactHook'un yazdığı dizin; FAIL koşumlardan sonra sunucuya kopyalanır.
    failure_artifacts_dir: str = "target/failure-artifacts"


class LiveProgressConfig(BaseModel):
    # Cucumber "message" plugin'inin yazdığı NDJSON dosyası; koşum sırasında tail edilir.
    cucumber_ndjson: str | None = None


class RetryConfig(BaseModel):
    """FAIL koşumdan sonra sadece kalan senaryoları bir kez yeniden koşma.

    Retry'da geçen senaryolar healing'e gitmez, 'flaky şüphesi' olarak
    işaretlenir (passed_on_retry). Cucumber tarafında `rerun:` plugin'i gerekir.
    """
    enabled: bool = True
    command: str  # ör: mvn -B test -Dcucumber.features=@target/rerun.txt
    rerun_file: str = "target/rerun.txt"


class AgentConfig(BaseModel):
    """Faz 2 healing ayarları (proje bazında).

    Her başarısız senaryo (locator kırılması dahil) aynı coding agent'a
    (opencode/Claude Code) gider — agent repoya tam erişimle dosyayı bulur,
    hatayı anlar, düzeltmeyi kendisi yapar. Sunucu kendi başına regex ile
    seçici çıkarıp JSON bekleyip metin değiştirmez; bu hem dar kapsamlıydı
    (tek satır/tek eşleşme dışında çalışmazdı) hem de modelin cevap
    biçimine bağımlıydı. Sınıflandırma (locator/logic/...) sadece agent'a
    hangi prompt şablonunun verileceğini seçmek için kullanılır.

    Agent'ın endpoint/model bilgisiyle sunucu ilgilenmez — opencode ve
    Claude Code zaten kendi kurulumlarında (opencode.json / claude
    ayarları, ANTHROPIC_BASE_URL vb.) sizin endpoint'inize (ör.
    https://api.sirketai.com.tr/v1) bağlıdır. Sunucu sadece o CLI'yı,
    terminalden çağırdığınızla birebir aynı şekilde çalıştırır.
    """
    agent_cli: str = "opencode"           # opencode | claude-code | custom
    agent_command: str | None = None      # agent_cli: custom için tam komut
                                          # (verilirse agent_cli'den önceliklidir)
    agent_model: str | None = None        # opsiyonel model override (--model);
                                          # boşsa CLI kendi varsayılanını kullanır
    env: dict[str, str] = Field(default_factory=dict)
    # Agent süreç ortamına eklenir. Genelde gerekmez (CLI zaten yapılandırılı);
    # binary PATH'te değilse HEAL_AGENT_BIN (tam yol) için kullanışlıdır.
    scenario_command: str                 # tek senaryoyu koşma (env: HEAL_SCENARIO)
    compile_command: str | None = None    # ör: mvn -B test-compile -q
    edit_whitelist: list[str] = Field(
        default_factory=lambda: ["src/test/java/"])
    command_timeout_s: int = 3600


class ProjectConfig(BaseModel):
    id: str
    name: str
    path: str
    command: str
    env: dict[str, str] = Field(default_factory=dict)
    results: ResultsConfig = Field(default_factory=ResultsConfig)
    live_progress: LiveProgressConfig = Field(default_factory=LiveProgressConfig)
    retry: RetryConfig | None = None
    agent: AgentConfig | None = None


class ServerConfig(BaseModel):
    auth_token: str
    data_dir: str = "data"
    keep_runs: int = 200  # proje başına saklanacak koşum sayısı (log + artefakt)
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
