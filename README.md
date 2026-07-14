# Test Runner Server

Sunucu/VM üzerinde çalışan, uzaktan **web arayüzüyle** test koşumu başlatılan
ve testlerin durumunu **canlı** (konsol çıktısı + geçme yüzdesi) gösteren hafif
test runner. Komut satırından çalışıp JUnit XML veya Cucumber JSON üreten
**her** test framework'ünü koşabilir; birincil hedef Java + Selenium +
Cucumber ve JavaFX + TestFX projeleridir.

```
Tarayıcı ──HTTP+WebSocket (token)──▶ FastAPI (VM)
  ├── projects.yaml   proje tanımları (yol, komut, rapor yolları)
  ├── Runner          subprocess: mvn test → canlı log akışı
  ├── Progress        Cucumber NDJSON tail → canlı geçme yüzdesi
  ├── Parsers         cucumber.json + surefire XML → kesin istatistik
  └── SQLite          koşum geçmişi (runs + scenario_results)
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
| `GET /api/runs/{id}` | Koşum detayı + senaryo sonuçları |
| `GET /api/runs/{id}/log` | Tam konsol logu (düz metin) |
| `WS /api/runs/{id}/stream?token=` | Canlı olaylar: `log`, `progress`, `finished` |

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

- **Faz 1 (bu repo):** runner + web arayüzü + canlı ilerleme + koşum geçmişi ✅
- **Faz 1.6:** başarısız senaryoları `rerun.txt` ile bir kez yeniden koşma,
  retry'da geçenleri "flaky şüphesi" olarak işaretleme
- **Faz 2:** LLM healing — hata sınıflandırma; locator kırılmalarında budanmış
  DOM + tek LLM çağrısı + deterministik patch; karmaşık hatalarda opencode
  (git worktree izolasyonu, diff whitelist, insan onaylı push).
  `examples/java-templates/` bu fazın Java tarafı hazırlığıdır.
- **Faz 3:** RAG + agent ile yeni test üretimi
