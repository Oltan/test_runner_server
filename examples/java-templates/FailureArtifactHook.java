// ŞABLON — kendi test projenize kopyalayıp uyarlayın (paket adı, TestContext sınıfı).
// Amaç: Senaryo FAIL olduğunda hata anının artefaktlarını diske yazmak.
// Bu artefaktlar Faz 2'de LLM healing pipeline'ının girdisidir:
//   target/failure-artifacts/<senaryo>/
//     ├── meta.json        (senaryo, hata, aktif sekme, sekme listesi)
//     ├── tab_0.html ...   (HER sekmenin DOM'u — çok sekmeli uygulamada
//     │                     "element yok" hatası aslında "yanlış sekme" olabilir)
//     ├── screenshot.png   (aktif sekme)
//     ├── console.log      (tarayıcı konsolu)
//     └── context.json     (shared state dump'ı — test nerede olduğunu sanıyordu)
//
// KURAL: Hook savunmacıdır — her yakalama adımı ayrı try/catch içindedir ve
// hook ASLA asıl test hatasını maskelemez / yeni hata fırlatmaz.

package hooks; // kendi paketinize göre değiştirin

import io.cucumber.java.After;
import io.cucumber.java.Scenario;
import org.openqa.selenium.OutputType;
import org.openqa.selenium.TakesScreenshot;
import org.openqa.selenium.UnhandledAlertException;
import org.openqa.selenium.WebDriver;
import org.openqa.selenium.logging.LogEntry;
import org.openqa.selenium.logging.LogType;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class FailureArtifactHook {

    // PicoContainer sizin shared state sınıfınızı buraya inject eder.
    // TestContext = driver'ı ve senaryolar arası taşınan durumu tutan sınıfınız.
    private final TestContext context;

    public FailureArtifactHook(TestContext context) {
        this.context = context;
    }

    // order yüksek → driver.quit() yapan @After hook'lardan ÖNCE çalışır.
    @After(order = 10000)
    public void captureOnFailure(Scenario scenario) {
        if (!scenario.isFailed()) {
            return;
        }
        WebDriver driver = context.getDriver();
        if (driver == null) {
            return;
        }

        Path dir = artifactDir(scenario);
        Map<String, Object> meta = new LinkedHashMap<>();
        meta.put("scenario", scenario.getName());
        meta.put("timestamp", LocalDateTime.now().toString());

        dismissAlertIfAny(driver); // açık alert getPageSource'u patlatır

        // 1) Aktif sekmenin screenshot'ı
        try {
            byte[] png = ((TakesScreenshot) driver).getScreenshotAs(OutputType.BYTES);
            Files.write(dir.resolve("screenshot.png"), png);
        } catch (Exception ignored) { }

        // 2) TÜM sekmelerin DOM + URL + title'ı
        try {
            String original = driver.getWindowHandle();
            List<Map<String, String>> tabs = new ArrayList<>();
            int i = 0;
            for (String handle : driver.getWindowHandles()) {
                Map<String, String> tab = new LinkedHashMap<>();
                tab.put("handle", handle);
                tab.put("active", String.valueOf(handle.equals(original)));
                try {
                    driver.switchTo().window(handle);
                    tab.put("url", driver.getCurrentUrl());
                    tab.put("title", driver.getTitle());
                    Files.writeString(dir.resolve("tab_" + i + ".html"),
                            driver.getPageSource(), StandardCharsets.UTF_8);
                    tab.put("dom_file", "tab_" + i + ".html");
                } catch (Exception e) {
                    tab.put("capture_error", e.getClass().getSimpleName());
                }
                tabs.add(tab);
                i++;
            }
            try { driver.switchTo().window(original); } catch (Exception ignored) { }
            meta.put("tabs", tabs);
        } catch (Exception ignored) { }

        // 3) Tarayıcı konsol logları (Chrome'da çalışır)
        try {
            StringBuilder sb = new StringBuilder();
            for (LogEntry entry : driver.manage().logs().get(LogType.BROWSER)) {
                sb.append(entry.getLevel()).append(' ')
                  .append(entry.getMessage()).append('\n');
            }
            Files.writeString(dir.resolve("console.log"), sb.toString(),
                    StandardCharsets.UTF_8);
        } catch (Exception ignored) { }

        // 4) Shared state dump'ı — TestContext'inize describe() gibi bir metot
        //    ekleyin: aktif page object, kullanılan test verisi vb.
        try {
            Files.writeString(dir.resolve("context.json"),
                    context.describeAsJson(), StandardCharsets.UTF_8);
        } catch (Exception ignored) { }

        try {
            Files.writeString(dir.resolve("meta.json"), toJson(meta),
                    StandardCharsets.UTF_8);
        } catch (Exception ignored) { }
    }

    private void dismissAlertIfAny(WebDriver driver) {
        try {
            driver.switchTo().alert().accept();
        } catch (Exception ignored) {
            // alert yoksa/kapanamadıysa devam — diğer adımlar kendi try/catch'inde
        }
    }

    private Path artifactDir(Scenario scenario) {
        String safe = scenario.getName()
                .replaceAll("[^\\p{L}\\p{N}_-]+", "_");
        String ts = LocalDateTime.now()
                .format(DateTimeFormatter.ofPattern("yyyyMMdd-HHmmss"));
        Path dir = Path.of("target", "failure-artifacts", safe + "-" + ts);
        try { Files.createDirectories(dir); } catch (Exception ignored) { }
        return dir;
    }

    // Bağımlılık eklememek için ilkel JSON üretimi; projenizde Jackson/Gson
    // varsa onu kullanın.
    @SuppressWarnings("unchecked")
    private String toJson(Object value) {
        if (value instanceof Map) {
            StringBuilder sb = new StringBuilder("{");
            ((Map<String, Object>) value).forEach((k, v) ->
                    sb.append('"').append(k).append("\":")
                      .append(toJson(v)).append(','));
            if (sb.charAt(sb.length() - 1) == ',') sb.setLength(sb.length() - 1);
            return sb.append('}').toString();
        }
        if (value instanceof List) {
            StringBuilder sb = new StringBuilder("[");
            for (Object item : (List<Object>) value) {
                sb.append(toJson(item)).append(',');
            }
            if (sb.charAt(sb.length() - 1) == ',') sb.setLength(sb.length() - 1);
            return sb.append(']').toString();
        }
        return '"' + String.valueOf(value)
                .replace("\\", "\\\\").replace("\"", "\\\"")
                .replace("\n", "\\n") + '"';
    }
}
