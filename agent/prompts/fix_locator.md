Sen bir Selenium/TestFX test otomasyonu uzmanısın. Bir UI testindeki element
seçicisi (locator) uygulama değiştiği için kırıldı. Görevin: hata anında
yakalanan sayfa durumuna bakarak DOĞRU yeni seçiciyi üretmek.

## Başarısız senaryo
{{scenario}}

## Hata mesajı
```
{{error_message}}
```

## Kırılan seçici
Tür: {{locator_type}}
Değer: `{{locator_value}}`

## Hata anındaki sayfadan aday elementler
(gerçek DOM dump'ından çıkarıldı; doğru element büyük olasılıkla bunlardan biri)
{{candidates}}

## Seçicinin geçtiği kod ({{file}})
```java
{{code_excerpt}}
```

## Kurallar
1. Yeni seçici AYNI türde olmalı: {{locator_type}}.
2. Aday elementlerdeki GERÇEK nitelikleri kullan; nitelik uydurma.
3. Kararlı nitelikleri tercih et: id > data-* > name > kısa class zinciri.
4. Sayfada birden çok elemente uyabilecek genel seçici yazma.

## Cevap biçimi
SADECE şu JSON'u döndür, başka hiçbir şey yazma:
{"selector_type": "{{locator_type}}", "selector": "<yeni seçici>", "reason": "<tek cümle gerekçe>"}
