# Görev: Deterministik test hatasını düzelt

Aşağıdaki Cucumber senaryosu üst üste iki koşumda da FAIL etti (flaky değil,
gerçek hata). Kök nedeni bul ve düzelt.

## Başarısız senaryo
Feature: {{feature}}
Senaryo: {{scenario}}

## Hata
```
{{error_message}}
```

## Hata anında yakalanan artefaktlar
{{artifacts_summary}}

## Kurallar (ihlal = öneri otomatik reddedilir)
1. SADECE şu dizinlerdeki dosyaları düzenle: {{whitelist}}
2. Feature (.feature) dosyalarını DEĞİŞTİRME — senaryo davranışı iş gereksinimidir.
3. Assertion'ı silerek/gevşeterek testi geçirme; beklenen değer gerçekten
   değiştiyse nedenini kod yorumunda açıkla.
4. `Thread.sleep` ekleme; bekleme gerekiyorsa WebDriverWait kullan.
5. Bu depodaki AGENTS.md kurallarına uy.

## Doğrulama
Düzeltmen şu komutla doğrulanacak (HEAL_SCENARIO ortam değişkeni senaryo adını içerir):
```
{{scenario_command}}
```
