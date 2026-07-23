# Test Runner Server

> 📖 **Sıfırdan kurulum, gerçek proje bağlama, healing devreye alma ve sorun
> giderme için adım adım rehber: [docs/KILAVUZ.md](docs/KILAVUZ.md)** —
> ilk kez kuruyorsanız oradan başlayın.

Sunucu/VM üzerinde çalışan, uzaktan **web arayüzüyle** test koşumu başlatılan
ve testlerin durumunu **canlı** (konsol çıktısı + geçme yüzdesi) gösteren hafif
test runner. Komut satırından çalışıp JUnit XML veya Cucumber JSON üreten
**her** test framework'ünü koşabilir; birincil hedef Java + Selenium +
Cucumber ve JavaFX + TestFX projeleridir.

```
Tarayıcı ──HTTP+WebSocket (token)──▶ FastAPI (VM)
  ├── projects.yaml   proje tanımları (yol, komut, rapor yolları, retry, agent)
  ├── Runner          subprocess: mvn test → canlı log akışı
  ├── Progress        Cucumber NDJSON tail → canlı geçme yüzdesi
  ├── Parsers         cucumber.json + surefire XML → kesin istatistik
  ├── Retry           FAIL senaryoları bir kez tekrarla → flaky ayrımı
  ├── Healing         LLM ile düzeltme önerisi (git worktree'de, insan onaylı)
  └── SQLite          koşum geçmişi (runs + scenario_results + heal_attempts)
```

## Hızlı başlangıç (sahte projeyle deneme)

```bash
pip install -r requirements.txt
uvicorn server.main:app --host 0.0.0.0 --port 8000
```

Tarayıcıdan `http://<sunucu>:8000` açın; token sorulduğunda `projects.yaml`
içindeki `auth_token` değerini girin (varsayılan `degistir-beni` —
**değiştirin**). "Örnek: Sahte Cucumber Simülasyonu" kartındaki **Çalıştır**
düğmesi, gerçek bir Java projesi olmadan canlı log + ilerleme akışını uçtan
uca gösterir.

## Kendi projenizi bağlama

### 1. Cucumber runner'ınıza plugin ekleyin (tek değişiklik)

```java
@CucumberOptions(plugin = {
    "json:target/cucumber-report.json",       // koşum sonu kesin istatistik
    "message:target/cucumber-messages.ndjson",// koşum SIRASINDA canlı ilerleme
    "rerun:target/rerun.txt"                  // Faz 1.6 retry için (şimdilik pasif)
})
```

POM / StepDefinitions / shared state yapınız sunucuyu etkilemez — sunucu
sadece `mvn test` çalıştırır ve çıktı dosyalarını okur.

### 2. projects.yaml'a tanımlayın

```yaml
projects:
  - id: web-otomasyon
    name: "Web Otomasyonu (Selenium + Cucumber)"
    path: /opt/projects/web-otomasyon      # VM'deki proje dizini
    command: "mvn -B test"
    env: { HEADLESS: "true" }
    results:
      cucumber_json: target/cucumber-report.json
      junit_xml_dir: target/surefire-reports   # cucumber_json yoksa fallback
    live_progress:
      cucumber_ndjson: target/cucumber-messages.ndjson
```

Cucumber olmayan projelerde `live_progress`'i boş bırakın; canlı konsol yine
çalışır, istatistik koşum sonunda `junit_xml_dir`'den gelir.

## Retry ve flaky ayrımı (Faz 1.6)

Projeye `retry` bölümü eklendiğinde, koşum FAIL ederse **sadece kalan
senaryolar** bir kez daha koşulur (Cucumber `rerun:` plugin'inin ürettiği
dosya üzerinden):

```yaml
    retry:
      enabled: true
      command: "mvn -B test -Dcucumber.features=@target/rerun.txt"
      rerun_file: target/rerun.txt
```

- Retry'da **geçen** senaryo → arayüzde `flaky şüphesi` rozeti
  (`passed_on_retry`). Bu senaryolar healing'e gönderilmez — sorun kodda
  değil, kararlılıktadır.
- Retry'da da **kalan** senaryo → deterministik hata, healing adayı.

## AI ile düzeltme — healing (Faz 2)

Deterministik FAIL eden senaryolar için koşum sayfasında **🩹 AI ile düzelt**
düğmesi çıkar. Her hata sınıfı (locator kırılması, assertion/mantık hatası)
**aynı coding agent'a** (opencode veya Claude Code — `agent_cli` ile
seçilir) gider; agent repoya tam erişimle dosyayı bulur, hatayı anlar,
düzeltmeyi kendisi yapar. Sunucu kendi başına regex/JSON/literal-patch
uğraşmaz — hata sınıfı sadece agent'a verilen görev metnindeki bağlamı
belirler (locator için budanmış DOM özeti + kırılan seçici; diğerleri için
hata + artefakt özeti).

Her deneme **izole git worktree'de, kendi `heal/<id>` branch'inde** yapılır:

```
sınıflandır (infra → insana işaretle) → worktree aç → görev metnini yaz →
agent'ı çalıştır (opencode/Claude Code — terminalde çalıştırdığınızla
birebir aynı argv) → diff whitelist kontrolü — dışarı dokunduysa RED →
(compile) → senaryoyu yeniden koş → diff'i arayüzde göster →
İNSAN ONAYI → branch kalır (merge/push size ait) | red → branch silinir
```

Güvenlik garantileri:
- Canlı test koşumlarının kullandığı dizine asla dokunulmaz (worktree izolasyonu).
- Agent `edit_whitelist` dışına dokunursa öneri otomatik reddedilir.
- Agent push/merge yapmaz; onaylanan düzeltme sadece branch olarak kalır.
- Canlı heal logunda görünen komut, agent'ın fiilen çalıştığı komuttur —
  gizli bir sarmalayıcı yok.

Gereksinimler: test projesi **git deposu** olmalı ve build çıktıları
(`target/` vb.) `.gitignore`'da olmalı; hata artefaktları için
`examples/java-templates/FailureArtifactHook.java` projeye eklenmiş olması
önerilir (locator düzeltmelerinde agent'a DOM bağlamı sağlar). opencode/
Claude Code kendi kurulumunuzda LLM endpoint'inize zaten bağlıdır — sunucu
bunu bilmez; yapılandırma örneği `projects.yaml` içindeki yorumlu bloktadır.
Agent prompt şablonları `agent/prompts/` altındadır, ihtiyaca göre
düzenlenebilir.

## VM kurulumu

```bash
# Ubuntu/Debian örneği
sudo apt install -y python3-pip openjdk-17-jdk maven
pip install -r requirements.txt

# Selenium için headless Chrome
sudo apt install -y chromium-browser chromium-chromedriver
# Testlerinizde: options.addArguments("--headless=new")

# JavaFX/TestFX için sanal ekran (en güvenilir yol)
sudo apt install -y xvfb
# projects.yaml'da command: "xvfb-run -a mvn -B test"
```

TestFX alternatifi (Monocle, xvfb'siz):
`-Dtestfx.headless=true -Dglass.platform=Monocle -Dmonocle.platform=Headless
-Dprism.order=sw` — ancak screenshot güvenilirliği için `xvfb-run` önerilir.

### systemd servisi

```ini
# /etc/systemd/system/test-runner.service
[Unit]
Description=Test Runner Server
After=network.target

[Service]
WorkingDirectory=/opt/test_runner_server
ExecStart=/usr/bin/python3 -m uvicorn server.main:app --host 0.0.0.0 --port 8000
Restart=on-failure
User=testrunner

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now test-runner
```

### Güvenlik

Tek paylaşımlı token vardır (`auth_token`). Sunucuyu internete açacaksanız
VPN/Tailscale arkasında tutun ya da reverse proxy (nginx/caddy) ile HTTPS
ekleyin. Aynı projede eşzamanlı ikinci koşum 409 ile reddedilir.

## API

| Uç | Açıklama |
|---|---|
| `GET /api/projects` | Tanımlı projeler + aktif/son koşum bilgisi |
| `POST /api/projects/{id}/run` | Koşum başlat → `{run_id}` (aktifse 409) |
| `POST /api/runs/{id}/stop` | Koşumu durdur (process group SIGTERM→SIGKILL) |
| `GET /api/runs?project=&limit=` | Koşum geçmişi |
| `GET /api/runs/{id}` | Koşum detayı + senaryolar + retry/heal bilgisi |
| `GET /api/runs/{id}/log` | Tam konsol logu (düz metin) |
| `WS /api/runs/{id}/stream?token=` | Canlı olaylar: `log`, `progress`, `finished` |
| `POST /api/runs/{id}/heal` | Healing başlat `{scenario, mode}` → `{heal_id}` |
| `GET /api/heals/{id}` | Heal durumu: aşamalar + diff |
| `POST /api/heals/{id}/approve` | Onayla: `heal/<id>` branch'i repoda kalır |
| `POST /api/heals/{id}/reject` | Reddet: branch + worktree silinir |

Kimlik doğrulama: `X-Auth-Token` header'ı veya `?token=` parametresi.

```bash
curl -H "X-Auth-Token: degistir-beni" http://localhost:8000/api/projects
curl -X POST -H "X-Auth-Token: degistir-beni" \
     http://localhost:8000/api/projects/fake-sim/run
```

## Geliştirme

```bash
pip install pytest httpx
python3 -m pytest tests/ -v
```

## Yol haritası

- **Faz 1:** runner + web arayüzü + canlı ilerleme + koşum geçmişi ✅
- **Faz 1.6:** retry + flaky işaretleme ✅
- **Faz 2 (sunucu tarafı):** LLM healing — tek agent akışı (opencode/Claude
  Code, worktree izolasyonu + diff whitelist + insan onayı); hata sınıfı
  sadece görev şablonunu seçer ✅ — kullanıcı tarafında kalanlar:
  `FailureArtifactHook`'un test projesine eklenmesi, opencode/Claude Code
  kurulumu ve `agent` yapılandırması
- **Faz 3:** RAG + agent ile yeni test üretimi; opsiyonel Playwright MCP
  eskalasyonu
