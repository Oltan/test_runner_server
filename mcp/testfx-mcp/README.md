# TestFX MCP Server

JavaFX uygulamalarını AI agent'larıyla (Claude Code, opencode, MCP destekleyen
her istemci) **canlı sürmek** için stdio tabanlı MCP (Model Context Protocol)
sunucusu — Playwright MCP'nin tarayıcı için yaptığını JavaFX için yapar.

JavaFX scene graph'a yalnızca uygulamanın kendi JVM'i içinden erişilebilir;
bu yüzden sunucu, hedef uygulamayı **kendi JVM'inde** TestFX `FxToolkit` ile
başlatır ve `FxRobot` ile sürer. Uygulamanızın koduna hiçbir ekleme gerekmez —
jar'ınızın classpath'e eklenmesi yeterlidir.

## Derleme

```bash
cd mcp/testfx-mcp
mvn -q package          # → target/testfx-mcp.jar (tek çalıştırılabilir fat-jar)
```

> Fat-jar, derlendiği platformun JavaFX native'lerini içerir: Linux'ta
> derlenen jar Linux'ta çalışır. Windows/macOS için o platformda derleyin.

## Hızlı deneme (kendi uygulamanız olmadan)

```bash
java -jar target/testfx-mcp.jar --headless --app-class testfxmcp.demo.DemoApp
```

stdin'den MCP konuşur; `initialize` → `tools/list` → `tools/call` akışıyla
gömülü `DemoApp` üzerinde uçtan uca deneyebilirsiniz.

## Kendi JavaFX uygulamanızla

Uygulamanızın jar'ını (ve bağımlılıklarını) classpath'e ekleyin:

```bash
java -cp target/testfx-mcp.jar:/opt/app/uygulamaniz.jar \
     testfxmcp.Main --app-class com.ornek.UygulamaFX
```

- `--app-class` verilmezse agent `launch_app` çağrısında `app_class`
  parametresiyle geçebilir.
- `--app-args "a b"` ile varsayılan uygulama argümanları verilebilir.
- Uygulamanız `javafx.application.Application`'ı extend etmelidir
  (standart JavaFX giriş sınıfı).

### Headless / ekranlı çalıştırma

| Kip | Komut | Not |
|---|---|---|
| **xvfb (önerilen)** | `xvfb-run -a java -cp ... testfxmcp.Main ...` | Screenshot'lar güvenilir |
| Monocle headless | `java ... testfxmcp.Main --headless ...` | xvfb gerektirmez; screenshot boş çıkabilir |
| Gerçek ekran | bayraksız | Masaüstünde geliştirme sırasında |

## MCP istemcisine bağlama

**Claude Code:**

```bash
claude mcp add testfx -- java -cp /opt/testfx-mcp.jar:/opt/app/uygulamaniz.jar \
    testfxmcp.Main --app-class com.ornek.UygulamaFX --headless
```

**opencode** (`opencode.json`):

```json
{
  "mcp": {
    "testfx": {
      "type": "local",
      "command": ["java", "-cp", "/opt/testfx-mcp.jar:/opt/app/uygulamaniz.jar",
                  "testfxmcp.Main", "--app-class", "com.ornek.UygulamaFX", "--headless"]
    }
  }
}
```

(Alan adlarını kurduğunuz sürümün dokümanıyla doğrulayın.)

## Tool'lar

| Tool | Parametreler | Açıklama |
|---|---|---|
| `launch_app` | `app_class?`, `args?` | Uygulamayı JVM içinde başlatır |
| `close_app` | — | Uygulamayı ve pencereleri kapatır |
| `get_scene_graph` | `max_depth?` | Scene graph JSON dökümü (fx_id, styleClass, metin, bounds…) |
| `find_nodes` | `query` | Sorguyla eşleşen node'ların özetleri |
| `click` | `query`, `button?`, `count?` | Tek/çift, sol/sağ/orta tık |
| `write_text` | `text`, `query?`, `clear?` | Alana tıklayıp yazar; `clear` içeriği önce siler |
| `press_keys` | `keys` | Tuş kombinasyonu, örn. `["CTRL","S"]` |
| `wait_for` | `query`, `timeout_ms?` | Node görünene dek bekler |
| `screenshot` | `query?` | PNG (MCP image content); boşsa tüm pencere |
| `list_windows` | — | Açık stage'ler: başlık, odak, boyut |

**Sorgu biçimleri** (TestFX sözdizimi): `#fxId`, `.styleClass` veya görünen
metin (örn. `"Kaydet"`). Doğru sorguyu bulmak için önce `get_scene_graph`
çağırın — tipik agent akışı:

```
launch_app → get_scene_graph → click/write_text/press_keys → wait_for → screenshot
```

Hatalar (node yok, zaman aşımı…) MCP `isError` sonucu olarak açıklayıcı
Türkçe mesajla döner; agent mesajdaki yönlendirmeyle kendini düzeltebilir.

## Testler

```bash
mvn -q test                 # Monocle headless duman testleri (gömülü DemoApp)
TESTFX_HEADED=1 mvn test    # gerçek ekranda (veya xvfb-run altında)
```

## Sınırlar (v1)

- Aynı anda tek uygulama (yeniden başlatmak için `close_app` → `launch_app`).
- Drag&drop, tablo/liste hücre seçimi gibi ileri etkileşimler henüz yok.
- `System.exit` çağıran uygulamalar sunucuyu da kapatır (JavaFX uygulamaları
  için olağan `Platform.exit` sorunsuzdur).
