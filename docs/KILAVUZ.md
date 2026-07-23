# Test Runner Server — Ayrıntılı Kurulum ve İşletme Kılavuzu

Bu belge, sistemi sıfırdan kurup gerçek projelerinizle çalıştırmanız ve
LLM healing'i devreye almanız için gereken **her adımı** içerir. Aşamalar
sıralıdır; her aşamanın sonunda bir **kontrol noktası** vardır — kontrol
noktasını geçmeden sonraki aşamaya geçmeyin. Bir şey ters giderse
[Sorun Giderme](#10-sorun-giderme) bölümüne bakın.

## İçindekiler

1. [Sistem nedir, nasıl çalışır](#1-sistem-nedir-nasıl-çalışır)
2. [Dosya haritası](#2-dosya-haritası)
3. [Aşama 0 — Kendi bilgisayarınızda 10 dakikada deneme](#3-aşama-0--kendi-bilgisayarınızda-10-dakikada-deneme)
4. [Aşama 1 — Sunucu/VM kurulumu](#4-aşama-1--sunucuvm-kurulumu)
5. [Aşama 2 — Gerçek Selenium+Cucumber projesini bağlama](#5-aşama-2--gerçek-seleniumcucumber-projesini-bağlama)
6. [Aşama 3 — Retry ve flaky ayrımı](#6-aşama-3--retry-ve-flaky-ayrımı)
7. [Aşama 4 — LLM healing kurulumu](#7-aşama-4--llm-healing-kurulumu)
8. [Aşama 5 — JavaFX / TestFX projesi](#8-aşama-5--javafx--testfx-projesi)
9. [API referansı](#9-api-referansı)
10. [Sorun giderme](#10-sorun-giderme)
11. [Veri dizini ve bakım](#11-veri-dizini-ve-bakım)
12. [Model ve agent seçimi](#12-model-ve-agent-seçimi)

---

## 1. Sistem nedir, nasıl çalışır

```
Sizin bilgisayarınız (tarayıcı)
        │  HTTP + WebSocket (X-Auth-Token)
        ▼
┌─ Sunucu/VM ──────────────────────────────────────────────┐
│  FastAPI (uvicorn, port 8000)                            │
│   ├─ projects.yaml  → proje tanımları                    │
│   ├─ Runner         → "mvn test" subprocess olarak koşar │
│   │                   stdout satır satır tarayıcıya akar │
│   ├─ Progress       → Cucumber'ın message (NDJSON)       │
│   │                   dosyasını tail eder → canlı % 	   │
│   ├─ Retry          → FAIL senaryoları 1 kez tekrarlar   │
│   │                   → geçen = flaky, kalan = gerçek    │
│   ├─ Healing        → gerçek hatalar için LLM önerisi    │
│   │                   (izole git worktree'de, onaylı)    │
│   └─ SQLite (data/) → koşum geçmişi, senaryolar, heal'ler│
│                                                          │
│  Test projeleriniz (aynı VM'de, ayrı dizinlerde):        │
│   /opt/projects/web-otomasyon   (Selenium+Cucumber)      │
│   /opt/projects/javafx-app      (TestFX)                 │
│                                                          │
│  vLLM (aynı ya da başka sunucuda): OpenAI-uyumlu API     │
└──────────────────────────────────────────────────────────┘
```

Temel fikirler:

- **Sunucu test dilinden bağımsızdır.** Sadece bir shell komutu çalıştırır
  (`mvn -B test` gibi) ve çıktı dosyalarını okur. POM/StepDefinitions/shared
  state yapınız sunucuyu hiç ilgilendirmez.
- **Canlı yüzde** Cucumber'ın `message` plugin'inin koşum sırasında yazdığı
  NDJSON dosyasından hesaplanır. Bu plugin yoksa canlı konsol yine çalışır,
  sadece yüzde koşum sonunda gelir.
- **Flaky ≠ bozuk.** Retry'da geçen senaryo "flaky şüphesi" alır ve healing'e
  gönderilmez — çünkü sorun kodda değildir, LLM'e düzelttirmek sahte
  değişiklik üretir.
- **Healing asla kendi başına kod değiştirmez.** Her deneme izole git
  worktree + `heal/<id>` branch'inde yapılır, diff size gösterilir; onaylarsanız
  branch repoda kalır (merge/push sizde), reddederseniz silinir.

## 2. Dosya haritası

| Yol | Ne işe yarar |
|---|---|
| `server/main.py` | REST + WebSocket API, statik dosya servisi, auth |
| `server/runner.py` | Koşum yaşam döngüsü: subprocess, canlı log, retry tetikleme, retention |
| `server/progress.py` | NDJSON tail → canlı senaryo sayacı |
| `server/parsers.py` | cucumber-report.json + surefire XML → istatistik |
| `server/db.py` | SQLite: runs, scenario_results, heal_attempts |
| `server/config.py` | projects.yaml şeması (pydantic) — tüm ayarların tanımı burada |
| `server/healing/` | Healing motoru: classify, locator, domprune, patch, workspace, llm, engine |
| `agent/prompts/` | LLM prompt şablonları — **düzenleyebilirsiniz** |
| `web/` | Arayüz: index (dashboard), run (canlı koşum), heal (AI düzeltme) |
| `projects.yaml` | Proje tanımları — sizin dolduracağınız ana dosya |
| `examples/fake-cucumber-sim/` | Java'sız uçtan uca deneme için sahte proje |
| `examples/heal-fixtures/` | Healing'i gerçek projenize dokunmadan test etme araçları |
| `examples/java-templates/` | Test projenize kopyalayacağınız Java dosyaları |
| `tests/` | Sunucunun kendi birim testleri (`python3 -m pytest tests/`) |
| `data/` | Çalışma verisi (git'te yok): SQLite, loglar, artefaktlar, worktree'ler |

## 3. Aşama 0 — Kendi bilgisayarınızda 10 dakikada deneme

Amaç: Java projesi olmadan, sahte simülatörle tüm akışı görmek.

**Gereksinim:** Python 3.11+ ve git. (Windows'ta: python.org kurulumunda
"Add python.exe to PATH" işaretli olsun; git = Git for Windows.)

**Linux/macOS:**

```bash
git clone <repo-url> test_runner_server
cd test_runner_server
git checkout claude/admiring-clarke-y7mcvc

python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# ÖNEMLİ: önce token'ı değiştirin
#   projects.yaml → auth_token: "kendi-gizli-tokeniniz"

uvicorn server.main:app --host 0.0.0.0 --port 8000
```

**Windows (PowerShell):**

```powershell
git clone <repo-url> test_runner_server
cd test_runner_server
git checkout claude/admiring-clarke-y7mcvc

python -m venv .venv
.venv\Scripts\Activate.ps1
# "running scripts is disabled" hatası alırsanız (bir kez, yönetici gerekmez):
#   Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
pip install -r requirements.txt

# ÖNEMLİ: projects.yaml → auth_token: "kendi-gizli-tokeniniz"
# (fake-sim komutu "{python} run.py" — sunucunun kendi Python'una çözülür,
#  Windows/Linux farkı için düzenleme GEREKMEZ)

uvicorn server.main:app --host 0.0.0.0 --port 8000
```

> Windows notu: `python` komutu Microsoft Store yönlendiricisine takılıyorsa
> (boş pencere açılıyorsa) Ayarlar → "App execution aliases" bölümünden
> python.exe takma adlarını kapatın veya `py -3` kullanın.

Tarayıcıdan `http://localhost:8000` açın. Token sorulduğunda
`projects.yaml`'daki değeri girin (token tarayıcının localStorage'ında
saklanır; yanlış girdiyseniz sayfa yenilenince tekrar sorar).

**"Örnek: Sahte Cucumber Simülasyonu"** kartında **▶ Çalıştır**'a basın:

1. Canlı koşum sayfası açılır; konsolda satırlar akar, üstte progress bar
   ve "geçen/kalan/geçme oranı" canlı güncellenir.
2. Koşum `FAILED` biter: 6✓ / 2✗ (bu kasıtlı — 1 flaky + 1 gerçek hata
   simüle edilir).
3. Mavi banner çıkar: **"otomatik retry koşumu başladı"** — tıklayıp retry'ı
   canlı izleyebilirsiniz (sadece 2 senaryo koşar: 1'i geçer, 1'i yine kalır).
4. Parent koşum sayfasına dönün (Son Koşumlar tablosundan): senaryo
   tablosunda **"Sipariş raporu indirilir"** senaryosunda turuncu
   **flaky şüphesi** rozeti, **"Boş rapor uyarısı"**nda hata mesajı görürsünüz.

> **KONTROL NOKTASI 0:** Canlı log + canlı yüzde + otomatik retry + flaky
> rozetini gördüyseniz çekirdek sistem çalışıyor demektir.

Sunucunun kendi testlerini de koşabilirsiniz:

```bash
pip install pytest
python3 -m pytest tests/ -v        # 24 test PASSED görmelisiniz
```

## 4. Aşama 1 — Sunucu/VM kurulumu

Amaç: Sistemin VM'de kalıcı servis olarak çalışması.

### 4.1 Paketler (Ubuntu/Debian örneği)

```bash
sudo apt update
sudo apt install -y python3-pip python3-venv git openjdk-17-jdk maven

# Selenium için headless Chrome
sudo apt install -y chromium-browser chromium-chromedriver
# (Google Chrome kullanıyorsanız kendi paketini + uyumlu chromedriver'ı kurun)

# JavaFX/TestFX için sanal ekran (Aşama 5'te gerekecek)
sudo apt install -y xvfb
```

### 4.2 Uygulama

```bash
sudo mkdir -p /opt/test_runner_server && sudo chown $USER /opt/test_runner_server
git clone <repo-url> /opt/test_runner_server
cd /opt/test_runner_server
git checkout claude/admiring-clarke-y7mcvc
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
# projects.yaml → auth_token'ı değiştirin
```

### 4.3 systemd servisi

`/etc/systemd/system/test-runner.service`:

```ini
[Unit]
Description=Test Runner Server
After=network.target

[Service]
WorkingDirectory=/opt/test_runner_server
Environment=CONFIG_PATH=/opt/test_runner_server/projects.yaml
ExecStart=/opt/test_runner_server/.venv/bin/uvicorn server.main:app --host 0.0.0.0 --port 8000
Restart=on-failure
User=testrunner          # testleri koşacak kullanıcı; Chrome'a erişimi olmalı

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now test-runner
sudo systemctl status test-runner      # "active (running)" görmelisiniz
journalctl -u test-runner -f           # canlı sunucu logu
```

### 4.4 Uzaktan erişim ve güvenlik

Tek paylaşımlı token vardır. Seçenekler (birini uygulayın):

- **En kolay/güvenli:** VM'yi VPN veya Tailscale arkasında tutun, portu
  internete hiç açmayın.
- **HTTPS ile açmak isterseniz:** nginx/caddy reverse proxy. nginx için
  kritik nokta WebSocket başlıklarıdır:

```nginx
server {
    listen 443 ssl;
    server_name test.sirket.local;
    # ssl_certificate ... ; ssl_certificate_key ... ;
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;     # WebSocket için şart
        proxy_set_header Connection "upgrade";      # WebSocket için şart
        proxy_read_timeout 3600s;                   # uzun koşumlar için
    }
}
```

### 4.5 Windows makinede sunucu çalıştırma (Linux VM yerine)

Sistem Windows'ta da tam çalışır; farklar şunlardır:

- **Komutlar:** projeleriniz için `command`/`retry.command` değerlerinde
  Windows'ta çalışan komutlar yazın (`mvn` Windows'ta `mvn.cmd`'yi bulur,
  değişiklik gerekmez; `xvfb-run` hiç yok — Windows'ta gerekmez de).
  Python tabanlı komutlarda `{python}` yer tutucusunu kullanın — sunucuyu
  çalıştıran yorumlayıcıya çözülür, `python`/`python3` farkı ortadan kalkar
  (fake-sim ve heal fixture'ları zaten böyle gelir).
- **Yollar:** `projects.yaml` içinde Windows yollarını **düz eğik çizgiyle**
  yazın: `path: C:/projects/web-otomasyon` (ters bölü YAML'da kaçış sorunu
  çıkarır).
- **Durdurma davranışı:** Linux'ta önce nazik SIGTERM + 10 sn sonra zorla
  öldürme yapılır; Windows'ta güvenilir nazik grup sinyali olmadığı için
  **Durdur** düğmesi süreç ağacını doğrudan `taskkill /T /F` ile indirir
  (mvn → java → chromedriver → chrome dahil). Sonuç aynıdır: koşum `stopped`.
- **Kalıcı servis:** systemd yoktur. En kolayı: sunucuyu bir Görev
  Zamanlayıcı (Task Scheduler) görevi olarak "At startup" tetikleyicisiyle
  çalıştırmak, ya da [NSSM](https://nssm.cc) ile Windows servisi yapmak:
  `nssm install TestRunner "C:\...\test_runner_server\.venv\Scripts\uvicorn.exe" "server.main:app --host 0.0.0.0 --port 8000"`
  (AppDirectory'yi repo köküne ayarlayın).
- **Güvenlik duvarı:** Uzak erişim için 8000 portuna gelen bağlantıya izin
  verin: `netsh advfirewall firewall add rule name="TestRunner" dir=in action=allow protocol=TCP localport=8000`
- **Healing komutları:** `scenario_command`/`agent_command` içinde bash'e özgü
  `$DEĞIŞKEN` yerine **`{scenario}`, `{prompt_file}`, `{model}` yer
  tutucularını** kullanın — bunları sunucu shell'den bağımsız doldurur,
  aynı yaml her iki platformda çalışır (bkz. 7.3).

### 4.6 Windows'ta platform davranışını doğrulama

Sunucu kodundaki platforma özel iki yol (süreç grubu başlatma ve durdurma)
için repoda **çalıştırılabilir bir test** var; Windows makinenizde koşun:

```powershell
.venv\Scripts\Activate.ps1
pip install pytest
python -m pytest tests\test_stop_tree.py -v     # taskkill yolunu SİZİN makinenizde test eder
python -m pytest tests -v                        # tüm birim testleri (26)
```

`test_stop_tree.py` gerçek bir süreç ağacı kurar (parent → child; mvn →
java → chrome zincirinin küçük modeli), Durdur akışını çağırır ve **child
sürecin de** öldüğünü heartbeat dosyalarıyla kanıtlar. Linux'ta `killpg`
yolunu, Windows'ta `taskkill /T /F` yolunu test eder — geçiyorsa Durdur
düğmesine güvenebilirsiniz.

Ardından elle duman testi (5 dk):
1. fake-sim'i koşun (`command: "python run.py"` düzeltmesiyle) → canlı log
   + yüzde + otomatik retry + flaky rozeti (Aşama 0'daki gibi).
2. Koşum sırasında **Durdur**'a basın → durum `stopped`, Görev
   Yöneticisi'nde python süreçleri kalmamalı.
3. Healing: `create.ps1` + `mock_llm.py` ile 7.1'deki Adım 1'i uygulayın →
   Mod A "proposed"a ulaşmalı, onayda branch fixture repoda kalmalı.

### 4.7 Windows ↔ Linux geçişi (aynı repoyu iki tarafta kullanmak)

Kod tarafı iki platformda da aynıdır; geçişte dikkat edilecek üç nokta var:

1. **`projects.yaml` makineye özgüdür** — yollar (`C:/projects` vs
   `/opt/projects`) ve komutlar (`python` vs `python3`, `xvfb-run`) farklı.
   Çözüm: makine başına ayrı dosya tutun ve sunucuyu `CONFIG_PATH` ile
   başlatın: `projects.windows.yaml`, `projects.linux.yaml`.
   (İkisi de repoda durabilir; hangi makinedeyseniz onu gösterirsiniz.)
2. **`data/` dizini taşınmaz.** Koşum kayıtları log dosyalarına mutlak
   yolla işaret eder; diğer işletim sistemine kopyalarsanız eski logların
   içeriği açılmaz (sistem çökmez, sadece geçmiş loglar boş görünür).
   Her makine kendi `data/`'sını üretsin — zaten `.gitignore`'dadır.
3. **Satır sonları `.gitattributes` ile sabitlendi** — `.sh`/`.py` dosyaları
   Windows'ta da LF kalır, Git Bash script'leri bozulmaz. Bu dosya repoya
   sonradan eklendiği için **mevcut bir Windows klonunda** bir kez şunu
   çalıştırın (yeni klonlarda gerekmez):
   `git add --renormalize . && git status` (değişiklik görünürse commit'leyin).

> **KONTROL NOKTASI 1:** Uzak bilgisayarınızın tarayıcısından arayüz
> açılıyor ve fake-sim koşumu Aşama 0'daki gibi çalışıyorsa sunucu hazır.

## 5. Aşama 2 — Gerçek Selenium+Cucumber projesini bağlama

### 5.1 Test projesinde tek değişiklik: Cucumber plugin'leri

**JUnit 4 runner kullanıyorsanız** (`@RunWith(Cucumber.class)`):

```java
@RunWith(Cucumber.class)
@CucumberOptions(
    features = "src/test/resources/features",
    glue = {"stepdefinitions", "hooks"},
    plugin = {
        "pretty",
        "json:target/cucumber-report.json",        // koşum sonu istatistik
        "message:target/cucumber-messages.ndjson", // CANLI yüzde (koşum sırasında yazılır)
        "rerun:target/rerun.txt"                   // retry için FAIL listesi
    }
)
public class TestRunner { }
```

**JUnit 5 (junit-platform-suite) kullanıyorsanız**,
`src/test/resources/junit-platform.properties`:

```properties
cucumber.plugin=pretty, json:target/cucumber-report.json, message:target/cucumber-messages.ndjson, rerun:target/rerun.txt
```

Bu değişiklikten sonra lokalde bir kez `mvn test` koşup üç dosyanın
gerçekten oluştuğunu kontrol edin:

```bash
ls target/cucumber-report.json target/cucumber-messages.ndjson target/rerun.txt
```

### 5.2 Headless Chrome

Testleriniz VM'de ekransız koşacak. Driver kurulumunuza ekleyin:

```java
ChromeOptions options = new ChromeOptions();
if ("true".equals(System.getenv("HEADLESS"))) {
    options.addArguments("--headless=new", "--window-size=1920,1080",
                         "--no-sandbox", "--disable-dev-shm-usage");
}
// Healing artefaktlarında tarayıcı konsolu logları da istiyorsanız (önerilir):
LoggingPreferences logPrefs = new LoggingPreferences();
logPrefs.enable(LogType.BROWSER, Level.ALL);
options.setCapability("goog:loggingPrefs", logPrefs);
```

`HEADLESS` değişkenini sunucu, `projects.yaml`'daki `env:` bölümünden geçirir —
lokalde çalışırken görsel modda kalırsınız.

### 5.3 Projeyi VM'ye koyun ve tanımlayın

```bash
sudo mkdir -p /opt/projects && sudo chown testrunner /opt/projects
git clone <test-projenizin-repo-url'i> /opt/projects/web-otomasyon
cd /opt/projects/web-otomasyon && mvn -B test-compile   # bağımlılıklar insin
```

`projects.yaml`'a ekleyin (yorumlu örneğin açılmış hali):

```yaml
  - id: web-otomasyon
    name: "Web Otomasyonu (Selenium + Cucumber)"
    path: /opt/projects/web-otomasyon
    command: "mvn -B test"
    env:
      HEADLESS: "true"
    results:
      cucumber_json: target/cucumber-report.json
      junit_xml_dir: target/surefire-reports
    live_progress:
      cucumber_ndjson: target/cucumber-messages.ndjson
```

Sunucuyu yeniden başlatın: `sudo systemctl restart test-runner`.

### 5.4 İlk gerçek koşum

Arayüzden **▶ Çalıştır**. Kontrol edecekleriniz:

- [ ] Konsolda Maven çıktısı canlı akıyor
- [ ] Senaryolar koştukça progress bar ve yüzde güncelleniyor
- [ ] Koşum bitince istatistik doğru (Cucumber'ın kendi özetiyle karşılaştırın)
- [ ] Senaryo tablosu dolu, FAIL olanlarda hata mesajı görünüyor
- [ ] **Durdur** düğmesi koşumu gerçekten kesiyor (Chrome süreçleri dahil —
  `ps aux | grep chrome` ile bakın)

> **KONTROL NOKTASI 2:** Yukarıdakilerin hepsi tamamsa çekirdek hedefiniz
> (uzaktan koşum + canlı takip) tamamlanmıştır. **Healing'e geçmeden önce
> 1-2 hafta bu şekilde koşum geçmişi biriktirin** — hangi testlerin flaky
> olduğu bu veriden ortaya çıkar.

## 6. Aşama 3 — Retry ve flaky ayrımı

Projeye `retry` bölümü ekleyin:

```yaml
    retry:
      enabled: true
      command: "mvn -B test -Dcucumber.features=@target/rerun.txt"
      rerun_file: target/rerun.txt
```

Nasıl çalışır:

1. Normal koşum FAIL ederse ve `rerun.txt` doluysa, sunucu **otomatik olarak**
   retry komutunu çalıştırır (`is_retry=1`, parent'a bağlı).
2. Cucumber `@target/rerun.txt` sözdizimiyle **sadece FAIL eden senaryoları**
   koşar (dosyada `features/x.feature:12` biçiminde satırlar vardır).
3. Retry'da geçen senaryolar parent koşumda `passed_on_retry` işareti alır →
   arayüzde **flaky şüphesi** rozeti. Bunlar healing'e kapalıdır.
4. Retry'da da kalanlar = deterministik hata = healing adayı.

Doğrulama: Bilerek bozuk bir locator commit'leyip koşun — retry'da da
kalmalı ve rozet almamalı; gerçekten flaky bir testiniz varsa rozet almalı.

> **Not:** Flaky eşleştirmesi senaryo **adıyla** yapılır. `Scenario Outline`
> örnekleri Cucumber raporlarında aynı adla görünebilir — outline'larınızda
> örnek başına ayırt edici ad üretiyorsanız sorun yok, değilse outline'ın
> tamamı tek senaryo gibi işlenir (bilinçli sadeleştirme).

## 7. Aşama 4 — LLM healing kurulumu

Sıra önemli: **önce 7.1 fixture testi (kendi projenize dokunmadan), sonra
7.2 Java hook'u, en son 7.3 gerçek projede deneme.**

### 7.1 Healing'i fixture ile test edin (projenize dokunmadan)

Repoda hazır script var; iki sahte "Java" projesi (git repo) oluşturur.
Çıktının sonunda `projects.yaml`'a yapıştırılacak hazır blok basılır:

```bash
# Linux/macOS:
bash examples/heal-fixtures/create.sh /opt/projects/heal-fixtures
```

```powershell
# Windows (PowerShell):
powershell -ExecutionPolicy Bypass -File examples\heal-fixtures\create.ps1
# (varsayılan hedef: %TEMP%\heal-fixtures; isterseniz dizin argümanı verin)
```

**Adım 1 — vLLM'siz kuru test (mock LLM ile):**

```bash
# mock LLM'i başlatın (sabit bir locator düzeltmesi döndürür, port 8199):
python3 examples/heal-fixtures/mock_llm.py &          # Linux/macOS
# Windows: ayrı bir terminalde → python examples\heal-fixtures\mock_llm.py
```

Script'in bastığı yaml bloğunu `projects.yaml`'a ekleyin (mock için
`base_url: "http://127.0.0.1:8199/v1"`), sunucuyu yeniden başlatın ve:

1. **heal-a** projesini koşun → FAIL eder (kasıtlı).
2. Senaryo tablosunda **🩹 AI ile düzelt** → heal sayfası açılır.
3. Aşamaların sırayla yeşillendiğini izleyin: worktree → locator çıkarımı →
   kod eşleşmesi → DOM budama → LLM önerisi → patch → senaryo doğrulama →
   diff + commit. Durum **proposed** olur, diff görünür.
4. **Onayla** → `cd /opt/projects/heal-fixtures/heal-fixture-a && git branch`
   → `heal/xxxx` branch'ini görmelisiniz; ana dizindeki dosya DEĞİŞMEMİŞ olmalı.

**Adım 2 — Gerçek endpoint ile aynı test:**

Önce şirket endpoint'ini doğrulayın:

```bash
curl https://api.sirketai.com.tr/v1/models \
  -H "Authorization: Bearer $SIRKETAI_API_KEY"
curl https://api.sirketai.com.tr/v1/chat/completions \
  -H "Authorization: Bearer $SIRKETAI_API_KEY" -H "Content-Type: application/json" \
  -d '{"model":"glm-5.2-fp8","messages":[{"role":"user","content":"merhaba"}]}'
```

Sonra fixture config'inde Mod A'nın `base_url`'ini `https://api.sirketai.com.tr/v1`,
`model`'i gerçek model adına çevirin ve Adım 1'i tekrarlayın. Gerçek model de
`//button[@id='submit-button-v2']` benzeri bir öneri üretmeli (fixture'daki
DOM dump'ında doğru cevap var — model DOM'a bakmayı beceriyorsa bulur).

**Adım 3 — Mod B (opencode/Claude Code) testi:** `heal-b` fixture'ı, gerçek
CLI'nın davranışını taklit eden bir sahte agent'la gelir (görev dosyasını
okuyup kodu düzelten script — `agent_cli` henüz ayarlı değildir). Önce bunu
koşup akışı görün (worktree → agent koşumu → whitelist → doğrulama →
proposed); sonra fixture config'ine `agent_cli: opencode` (veya
`claude-code`) ekleyip `env.HEAL_AGENT_BIN` satırını kaldırarak gerçek
CLI'nızla tekrarlayın (bkz. 7.3 — CLI zaten kendi ayarlarıyla
`api.sirketai.com.tr`'ye bağlı olmalı, ekstra config gerekmez).

> **KONTROL NOKTASI 4a:** Fixture'da hem Mod A hem Mod B "proposed"a
> ulaşıyor ve onay/red branch davranışı doğruysa motor tarafı hazır.

### 7.2 Test projenize artefakt hook'u ekleyin

Healing'in "gözleri" budur: hata anında DOM + screenshot + shared state
yakalanmazsa Mod A çalışamaz ("Hata artefaktı bulunamadı" der).

1. `examples/java-templates/FailureArtifactHook.java` dosyasını test
   projenizin `hooks/` paketine kopyalayın; başındaki `package` satırını
   düzeltin.
2. Sınıf, sizin shared state sınıfınızı (PicoContainer'ın inject ettiği,
   genelde `TestContext` benzeri) constructor'dan alır. İki metoda ihtiyacı
   var — yoksa ekleyin:

```java
public class TestContext {
    // ... mevcut alanlarınız (driver, aktif sayfa, test verisi...)

    public WebDriver getDriver() { return this.driver; }

    /** Healing için: testin o an "nerede olduğunu" özetleyen JSON. */
    public String describeAsJson() {
        return String.format(
            "{\"activePage\":\"%s\",\"testData\":\"%s\"}",
            activePage != null ? activePage.getClass().getSimpleName() : "null",
            String.valueOf(currentTestData).replace("\"", "'"));
    }
}
```

3. Hook `order = 10000` ile gelir → driver'ı kapatan kendi `@After`
   hook'larınızın order'ı bundan **küçük** olmalı (varsayılan 10000'dir;
   çakışıyorsa kendi hook'unuza `@After(order = 500)` verin — Cucumber'da
   yüksek order önce çalışır).
4. `glue` listenizde `hooks` paketi olduğundan emin olun.
5. Lokalde bilerek bozuk bir locator ile koşup kontrol edin:
   `target/failure-artifacts/<senaryo>/` altında `tab_0.html`, `screenshot.png`,
   `meta.json`, `context.json` oluşmalı. **Bunu görmeden ilerlemeyin.**
6. `examples/java-templates/AGENTS.md`'yi test projenizin köküne kopyalayıp
   içindeki dizin adlarını/komutları kendi yapınıza göre düzeltin
   (Mod B'de agent bunu okur).

### 7.3 Gerçek projede agent yapılandırması

> **"opencode/Claude Code nerede çağrılıyor?"** Sunucu, o CLI'yı **aynen
> siz terminalden başlatmışsınız gibi** çalıştırır — gerçek argv listesi
> olarak (`server/healing/agents.py` → `build_agent_argv`), shell'e hiç
> girmeden. Yani ortada bir Python sarmalayıcı/aracı kütüphane yok; canlı
> heal logunda gördüğünüz `$ opencode run --model ... "<görev>"` satırı
> **fiilen çalışan komutun kendisidir** — kopyalayıp terminalinize
> yapıştırsanız birebir aynı işi yapar. Sunucunun tek işi: worktree'ye
> görev metnini yazmak (`HEAL_TASK.md`, kayıt amaçlı), cwd'yi o worktree
> yapmak, komutu argv olarak çalıştırmak; agent bitince diff whitelist +
> doğrulama zinciri devreye girer.
>
> **Endpoint/model bilgisiyle sunucu hiç ilgilenmez.** opencode ve Claude
> Code zaten kendi kurulumunuzda şirketinizin endpoint'ine
> (`https://api.sirketai.com.tr/v1`) bağlı — bu bağlantı `opencode.json`
> içinde veya Claude Code'un kendi ayarlarında/env değişkenlerinde
> tanımlıdır, **`projects.yaml`'a hiçbir şey yazmanıza gerek yok.** Siz
> sadece hangi CLI'yı çağıracağını söylersiniz.
>
> Altın kural: **CLI'yı önce sunucusuz, düz terminalde çalıştırıp
> doğrulayın** — terminalde çalışmayan komut sunucudan da çalışmaz.

Projenizin `projects.yaml` girdisine ekleyin — bu kadar:

```yaml
    agent:
      llm:                                   # Mod A — locator düzeltme
        # Bu, agent DEĞİL: sunucunun tek atımlık HTTP çağrısı attığı endpoint.
        base_url: "https://api.sirketai.com.tr/v1"
        model: "glm-5.2-fp8"                 # şirket endpoint'inizdeki model adı
        api_key_env: "SIRKETAI_API_KEY"      # anahtar bu env değişkeninden okunur

      agent_cli: opencode                    # Mod B — opencode | claude-code | custom
      # agent_model: "glm-5.2-fp8"           # opsiyonel: --model ile zorlar;
                                             # vermezseniz CLI'nın kendi
                                             # varsayılan modelini kullanır
      scenario_command: mvn -B test -Dcucumber.filter.name="{scenario}"
      compile_command: "mvn -B test-compile -q"
      edit_whitelist:
        - src/test/java/pages/
        - src/test/java/stepdefinitions/
```

`agent_cli` tam olarak ne çalıştırır (argv olarak — aşağıdaki gösterim
sırasıyla birebir):

| `agent_cli` | Sunucunun çalıştırdığı komut | Endpoint/model nereden geliyor |
|---|---|---|
| `opencode` | `opencode run [--model <agent_model>] "<görev>"` | test reponuzdaki `opencode.json` — sizin kurduğunuz |
| `claude-code` | `claude -p "<görev>" --permission-mode acceptEdits --allowedTools ... [--model <agent_model>]` | Claude Code'un kendi ayarları/env değişkenleri — sizin kurduğunuz |
| `custom` | `agent_command` satırınızı aynen (shell string, yer tutucularla) | tam kontrol sizde |

`agent_model` boşsa `--model` bayrağı **hiç eklenmez** — CLI kendi
varsayılan modelini kullanır. `<görev>` argümanı, hata anındaki senaryo +
artefakt özetini içeren tam metindir (uzun olabilir); argv olarak
geçirildiği için shell tırnak/kaçış karakteri sorunu yaşamaz.

**Önce sunucusuz doğrulama** (kurulumunuzun gerçekten çalıştığından emin olun):

```bash
cd /opt/projects/web-otomasyon      # test reponuzun içinde
opencode run "Bu repoda pages/ altında hangi sınıflar var?"
# veya:
claude -p "Bu repoda pages/ altında hangi sınıflar var?" --permission-mode acceptEdits
```

Cevap doğru geliyorsa (yani CLI zaten `api.sirketai.com.tr`'ye bağlıysa)
`projects.yaml`'da sadece `agent_cli: opencode` (veya `claude-code`) yazmanız
yeterli — başka hiçbir ayar gerekmez.

Diğer ayrıntılar:

- **Proje git deposu olmalı** ve `target/` `.gitignore`'da olmalı (yoksa
  Mod B'nin whitelist kontrolü build çıktılarını ihlal sanır).
- **Binary PATH'te değilse:** `agent.env` ile tam yolu verin, örn.
  `env: { HEAL_AGENT_BIN: "C:/Users/.../opencode.cmd" }` (Windows'ta sık
  gerekir). Ek CLI argümanı eklemek isterseniz `HEAL_AGENT_ARGS`; Claude
  Code'un izinli araç listesini değiştirmek isterseniz `HEAL_ALLOWED_TOOLS`.
- **Yer tutucular** (`custom` için): `{scenario}`, `{prompt_file}`, `{model}`,
  `{python}` komut çalıştırılmadan önce sunucu tarafından doldurulur —
  shell'den bağımsızdır, Windows'ta da Linux'ta da aynen çalışır.

### 7.4 Healing'i kullanma (günlük akış)

1. Koşum FAIL eder → otomatik retry → yine kalan senaryolar gerçek hatadır.
2. Koşum sayfasında senaryonun yanındaki **🩹 AI ile düzelt**'e basın.
   Hata sınıfına göre otomatik Mod A/B seçilir (infra/unknown hatalar
   reddedilir — onlar ortam sorunudur, elle bakın).
3. Heal sayfasında aşamaları izleyin. Süre: Mod A genelde 1-2 dk
   (senaryo koşumu dahil), Mod B agent'a bağlı.
4. **proposed** olunca diff'i okuyun:
   - Mantıklıysa **Onayla** → branch repoda kalır. Sonra kendi
     bilgisayarınızda: `git fetch && git log heal/<id> && git diff main...heal/<id>`
     → inceleyin, merge/PR edin. Merge sonrası VM'deki proje dizininde
     `git pull` yapmayı unutmayın.
   - Beğenmediyseniz **Reddet** → branch ve worktree silinir, iz kalmaz.
5. `needs_human` durumu = motor bilerek durdu (ör. locator kodda birden çok
   yerde geçiyor). Aşama detayındaki gerekçeyi okuyup elle düzeltin.

> **KONTROL NOKTASI 4b:** Gerçek projenizde bilerek bir locator bozup
> (`git commit` etmeden değil — commit'leyin, çünkü worktree HEAD'den açılır!)
> tam zinciri bir kez yaşayın: koşum FAIL → retry → heal → diff → onay →
> branch'i inceleyip geri alın.

## 8. Aşama 5 — JavaFX / TestFX projesi

1. VM'de koşum komutu: `xvfb-run -a mvn -B test` (Monocle'a göre daha
   güvenilir; screenshot'lar boş çıkmaz).
2. `projects.yaml` girdisinde `live_progress` kullanmayın (TestFX'te Cucumber
   yoksa) — istatistik `junit_xml_dir: target/surefire-reports`'tan gelir.
   TestFX'i Cucumber ile sarıyorsanız Selenium'daki kurulum aynen geçerlidir.
3. Healing artefaktları için `examples/java-templates/SceneGraphDumper.java`'yı
   projenize kopyalayın; test FAIL olduğunda çağırın:

```java
@AfterEach
void captureOnFailure(TestInfo info) {
    if (testFailed) {
        SceneGraphDumper.dumpAllWindows(Path.of("target", "failure-artifacts",
            sanitize(info.getDisplayName()), "scenegraph.json"));
        // + screenshot: robot.capture(...) / Scene.snapshot(...)
    }
}
```

4. Scene graph dump'ı DOM yerine geçer; healing pipeline'ı aynı şekilde çalışır
   (TestFX'in `NodeQueryException`'ı locator sınıfına girer).

## 9. API referansı

Tüm uçlar `X-Auth-Token` header'ı (veya `?token=`) ister.

```bash
TOKEN="kendi-tokeniniz"; BASE="http://VM:8000"

# Projeler + son koşum durumları
curl -H "X-Auth-Token: $TOKEN" $BASE/api/projects

# Koşum başlat (201 → {"run_id": ...} | 409 → zaten koşuyor)
curl -X POST -H "X-Auth-Token: $TOKEN" $BASE/api/projects/web-otomasyon/run

# Koşum durumu + senaryolar + retry/heal bilgisi
curl -H "X-Auth-Token: $TOKEN" $BASE/api/runs/<run_id>

# Koşumu durdur / tam log
curl -X POST -H "X-Auth-Token: $TOKEN" $BASE/api/runs/<run_id>/stop
curl -H "X-Auth-Token: $TOKEN" $BASE/api/runs/<run_id>/log

# Healing
curl -X POST -H "X-Auth-Token: $TOKEN" -H "Content-Type: application/json" \
     -d '{"scenario":"Sipariş gönderilir","mode":"auto"}' \
     $BASE/api/runs/<run_id>/heal
curl -H "X-Auth-Token: $TOKEN" $BASE/api/heals/<heal_id>
curl -X POST -H "X-Auth-Token: $TOKEN" $BASE/api/heals/<heal_id>/approve   # veya /reject
```

WebSocket: `ws://VM:8000/api/runs/<run_id>/stream?token=...` —
olaylar: `{"type":"backlog"|"log"|"progress"|"finished"}`.

`mode` değerleri: `auto` (sınıfa göre A/B), `a` (locator pipeline'a zorla),
`b` (agent'a zorla — unknown sınıfı hatalarda kullanışlı).

## 10. Sorun giderme

**Kurulum/koşum:**

| Belirti | Muhtemel neden → çözüm |
|---|---|
| Arayüz açılıyor ama her istek 401 | Token yanlış → tarayıcıda localStorage'ı temizleyin (Geliştirici Araçları → Application) veya sayfayı yenileyip doğru token'ı girin |
| "Proje dizini yok" (400) | `projects.yaml`'daki `path` VM'de yok veya servis kullanıcısı okuyamıyor → `sudo -u testrunner ls <path>` |
| 409 "koşum zaten aktif" | Aynı projede ikinci koşum engellenir (tasarım gereği) → mevcut koşumu bekleyin/durdurun. Retry koşumu da projeyi meşgul eder. |
| Koşum `error` bitiyor, istatistik yok | Test komutu test koşamadan çöktü → koşum sayfasındaki konsolu okuyun (genelde Maven/bağımlılık/Chrome sorunu) |
| Canlı yüzde hiç güncellenmiyor | `message` plugin'i ekli değil veya `cucumber_ndjson` yolu yanlış → koşum sonrası `ls <proje>/target/cucumber-messages.ndjson` |
| İstatistik hep 0/0 | `cucumber_json` yolu yanlış veya rapor üretilmiyor → `results:` yollarını dosya sistemiyle karşılaştırın |
| Durdurulan koşumda istatistik görünüyor | Görünmemeli — koşum başlangıcından eski raporlar zaten yok sayılır; görüyorsanız saat senkronu bozuk olabilir (`timedatectl`) |
| Chrome açılmıyor (headless) | `--no-sandbox --disable-dev-shm-usage` eklediniz mi? chromedriver ile Chrome sürümü uyumlu mu? |
| **Windows:** koşum anında `error`, logda "python3 ... not found" | Windows'ta `python3` komutu yoktur → kendi yazdığınız komutlarda `python` ya da `{python}` yer tutucusunu kullanın (repoyla gelen örnekler zaten `{python}` kullanır) |
| **Windows:** `python` boş pencere açıyor / Store'a gidiyor | Ayarlar → App execution aliases → python takma adlarını kapatın, ya da komutlarda `py -3` kullanın |
| **Windows:** `.venv\Scripts\Activate.ps1` "running scripts is disabled" | Bir kez: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| **Windows:** Durdur düğmesi süreçleri sert kapatıyor | Normaldir — Windows'ta nazik grup sinyali güvenilir olmadığından `taskkill /T /F` kullanılır; koşum yine düzgün `stopped` işaretlenir |
| **Windows:** uzak makineden arayüz açılmıyor ama lokalde açılıyor | Güvenlik duvarı → `netsh advfirewall firewall add rule name="TestRunner" dir=in action=allow protocol=TCP localport=8000` |

**Retry/flaky:**

| Belirti | Çözüm |
|---|---|
| Retry hiç tetiklenmiyor | `retry.enabled: true` mı? `rerun_file` yolu doğru mu? Dosya koşum sonrası dolu mu? (`rerun:` plugin'i ekli mi?) |
| Retry tüm testleri koşuyor | Retry komutunda `-Dcucumber.features=@target/rerun.txt` sözdizimini kontrol edin (@'e dikkat) |
| Flaky rozeti hiç çıkmıyor | Rozet parent koşumun sayfasındadır, retry'ınkinde değil. Senaryo adları parent/retry raporlarında birebir aynı mı? |

**Healing:**

| Belirti | Çözüm |
|---|---|
| "Bu projede agent yapılandırması yok" | `projects.yaml`'a `agent:` bloğu ekleyip servisi yeniden başlatın |
| "Proje bir git deposu değil" | Test projesinin kendi `.git`'i yok → o proje dizininde `cd <path> && git init && git add -A && git commit -m init` |
| "başka bir reponun alt klasörü olarak görünüyor" | Test projenizi test_runner_server'ın (veya başka bir reponun) klasör ağacının İÇİNE koymuşsunuz ve kendi `.git`'i yok — git üst dizine bakıp yanlış reponun altında sanıyor. Test projesini test_runner_server'ın dışına, ayrı bir klasöre taşıyın (veya kendi `.git`'ini oluşturun) |
| "Hata artefaktı bulunamadı" | `FailureArtifactHook` projede değil/çalışmıyor → 7.2'deki lokal doğrulamayı yapın; hook'un `@After` order'ı driver.quit'ten önce mi? |
| "Hata mesajından locator çıkarılamadı" | Hata Selenium'un standart biçiminde değil → heal'i `mode:"b"` ile agent'a zorlayın |
| "Locator kod içinde bulunamadı" | Locator kodda string birleştirmeyle üretiliyor olabilir (dinamik XPath) → bu sınıf otomatik patch'lenemez, elle düzeltin |
| `needs_human` | Kasıtlı durma (çoklu eşleşme, tür değişikliği önerisi) → aşama detayındaki gerekçeyi okuyun |
| LLM çağrısı başarısız | `curl <base_url>/models` ile endpoint'i doğrulayın; sunucudan vLLM'e ağ erişimi var mı? |
| Mod B: "whitelist DIŞINA dokundu" | Agent taşkınlık yaptı (koruma çalıştı) → `edit_whitelist`'i gözden geçirin ya da AGENTS.md kurallarını netleştirin; `target/` gitignore'da mı? |
| **Windows:** agent/senaryo komutu `$HEAL_...` değişkenini çözmüyor | `$VAR` bash sözdizimidir, cmd anlamaz → komutlarda `{scenario}` / `{prompt_file}` / `{model}` yer tutucularını kullanın (7.3) veya komutu `bash -lc '...'` ile sarın (Git Bash) |
| Yarıda kalan heal / kalıntı worktree | Sunucu heal ortasında yeniden başladıysa: proje dizininde `git worktree list` → `git worktree prune` → kalan `heal/*` branch'lerini `git branch -D` ile silin |

## 11. Veri dizini ve bakım

```
data/
├── runs.db          # SQLite: koşumlar, senaryo sonuçları, heal denemeleri
├── logs/<run_id>.log
├── artifacts/<run_id>/   # FAIL koşumların failure-artifacts kopyası
└── worktrees/<heal_id>/  # aktif heal'lerin çalışma alanı (bitince silinir)
```

- Retention otomatiktir: proje başına en yeni `keep_runs` (varsayılan 200)
  koşum tutulur; eskilerin log/artefaktları silinir.
- Yedeklemek isterseniz `data/runs.db` yeterlidir.
- Sunucu güncellemesi: `git pull && sudo systemctl restart test-runner`
  (aktif koşum varsa kesilir — boş bir anda yapın).

## 12. Model ve agent seçimi

Mevcut filonuzla önerilen dağılım:

| Rol | Model | Gerekçe |
|---|---|---|
| Mod A (locator, tek çağrı) | `qwen3.6-35b-a3b` | Görev dar/şablonlu; en hızlı model. En sık çalışan yol budur. |
| Mod B (agent) | `glm-5.2-fp8` | Agentic tarafı güçlü; 128k context yeterli çünkü pipeline görevi ~20-50k token'da paketler |
| Mod B eskalasyon + Faz 3 | `qwen3.5-397b-a17b` | İnatçı hatalar ve 256k context gerektiren test üretimi |

Agent CLI seçimi (opencode / Claude Code): `agent_cli` tek alan olduğundan
ikisini de `heal-b` fixture'ıyla A/B test edip kazananı yazın (bkz. 7.1).
Hangisini seçerseniz seçin diff whitelist + insan onayı korumaları aynıdır —
CLI değişse de motor davranışı değişmez.

---

*Sistemin tasarım kararları ve fazların gerekçeleri için `README.md`'ye,
prompt şablonlarını özelleştirmek için `agent/prompts/` dizinine bakın.*
