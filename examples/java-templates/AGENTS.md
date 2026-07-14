# AGENTS.md ŞABLONU — test projenizin köküne kopyalayıp uyarlayın

> Bu dosya, Faz 2'de test hatalarını düzelten coding agent'ın (opencode)
> her çağrıda otomatik okuduğu sabit talimat setidir. Kısa tutun; buradaki
> her satır her LLM çağrısında context'e girer.

## Proje yapısı

- Cucumber + Selenium, Java, Maven.
- Page Object Model: `src/test/java/pages/` — locator'lar burada tanımlı.
- Step definitions: `src/test/java/stepdefinitions/`.
- Feature dosyaları: `src/test/resources/features/`.
- Shared state: `TestContext` sınıfı PicoContainer ile step sınıflarına inject
  edilir; senaryolar arası veri (driver, aktif sayfa, test verisi) burada taşınır.

## Tek senaryoyu koşma

```bash
mvn -B test -Dcucumber.filter.name="<senaryo adı>"
```

Bir feature dosyasını koşma:

```bash
mvn -B test -Dcucumber.features=src/test/resources/features/<dosya>.feature
```

## Kurallar

1. SADECE şu dizinleri düzenleyebilirsin: `src/test/java/pages/`,
   `src/test/java/stepdefinitions/`.
2. Feature (.feature) dosyalarını DEĞİŞTİRME — senaryo davranışı iş
   gereksinimidir, testi geçirmek için gevşetilemez.
3. Locator düzeltirken: önce `target/failure-artifacts/` altındaki DOM
   dump'ına bak; locator'ı oradaki gerçek elemente göre güncelle. Kararlı
   nitelikleri tercih et: id > data-* > name > kısa CSS > XPath (en son çare).
4. Assertion'ı silerek/gevşeterek test geçirme. Beklenen değer değiştiyse
   nedenini yorumda belirt.
5. `Thread.sleep` ekleme; bekleme gerekiyorsa WebDriverWait/ExpectedConditions.
6. Değişiklikten sonra önce başarısız senaryoyu, geçerse ilgili feature'ı koş.
7. pom.xml, konfigürasyon ve CI dosyalarına dokunma.
