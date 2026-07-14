# Java şablonları (Faz 2 hazırlığı)

Bu klasördeki dosyalar **bu repoda derlenmez** — kendi test projenize
kopyalayıp uyarlayacağınız referans şablonlardır. Faz 2'deki LLM healing
pipeline'ı bu şablonların ürettiği artefaktları girdi olarak kullanır.

| Dosya | Nereye | Ne işe yarar |
|---|---|---|
| `FailureArtifactHook.java` | Selenium+Cucumber projenizin `hooks/` paketine | Senaryo FAIL olunca tüm sekmelerin DOM'u, screenshot, konsol logları ve shared state dump'ını `target/failure-artifacts/` altına yazar |
| `SceneGraphDumper.java` | TestFX projenizin test kaynaklarına | Test FAIL olunca JavaFX scene graph'ını (DOM karşılığı) JSON'a döker |
| `AGENTS.md` | Test projenizin köküne | Coding agent'ın (opencode) her çağrıda okuduğu proje kuralları |

## Uyarlama notları

- `FailureArtifactHook` içindeki `TestContext`, sizin shared state
  sınıfınızdır (PicoContainer ile inject edilen). İki metot beklenir:
  `getDriver()` ve `describeAsJson()` (aktif sayfa/test verisi özeti —
  yoksa basitçe `toString()` döndüren bir metot ekleyin).
- Hook `order = 10000` ile, driver'ı kapatan `@After` hook'larınızdan
  **önce** çalışacak şekilde ayarlıdır; kendi hook'larınızın order'ı
  daha düşük (varsayılan 10000'den küçük) olmalıdır.
- Cucumber runner'ınızda şu plugin'ler tanımlı olmalıdır (Faz 1 için de gerekli):

```java
@CucumberOptions(plugin = {
    "json:target/cucumber-report.json",
    "message:target/cucumber-messages.ndjson",
    "rerun:target/rerun.txt"
})
```
