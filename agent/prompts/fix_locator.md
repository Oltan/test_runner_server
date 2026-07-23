# Görev: Kırılan element seçicisini (locator) düzelt

Bir UI testindeki element seçicisi (locator/XPath/CSS) uygulama değiştiği
için kırıldı. Bu senaryo üst üste iki koşumda da FAIL etti (flaky değil,
gerçek hata). Repoya tam erişimin var — dosyayı bul, hatayı anla, kodu
doğrudan düzenle. **JSON veya belirli bir biçimde cevap döndürmene gerek
yok**; görevin kaynak dosyayı düzeltmek.

## Başarısız senaryo
{{scenario}}

## Hata mesajı
```
{{error_message}}
```

## Hata mesajından çıkarılan kırılan seçici (bulunabildiyse)
{{locator_line}}

## Muhtemel dosya (otomatik arama sonucu — kesin değil, kendin de arayabilirsin)
{{hint_file}}

## Hata anındaki sayfadan aday elementler (gerçek DOM dump'ından, budanmış)
{{dom_context}}

## Kurallar (ihlal = öneri otomatik reddedilir)
1. SADECE şu dizinlerdeki dosyaları düzenle: {{whitelist}}
2. Feature (.feature) dosyalarını DEĞİŞTİRME — senaryo davranışı iş gereksinimidir.
3. Kararlı nitelikleri tercih et: id > data-* > name > kısa CSS zinciri > XPath (son çare).
4. Aday elementlerdeki GERÇEK nitelikleri kullan; nitelik uydurma.
5. Düzeltme tek bir seçici satırından ibaret değilse (sayfa yapısı köklü
   değişmiş, birden fazla yer güncellenmeli, yardımcı metot gerekiyor gibi)
   — gerekeni yap, kendini tek satır değişikliğe sınırlama.
6. `Thread.sleep` ekleme; bekleme gerekiyorsa WebDriverWait kullan.
7. Bu depodaki AGENTS.md kurallarına uy.

## Doğrulama
Düzeltmen şu komutla doğrulanacak (HEAL_SCENARIO ortam değişkeni senaryo adını içerir):
```
{{scenario_command}}
```
