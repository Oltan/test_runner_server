package testfxmcp;

import javafx.application.Application;
import javafx.embed.swing.SwingFXUtils;
import javafx.scene.Node;
import javafx.scene.image.Image;
import javafx.scene.input.KeyCode;
import javafx.scene.input.MouseButton;
import javafx.stage.Stage;
import javafx.stage.Window;

import org.testfx.api.FxRobot;
import org.testfx.api.FxToolkit;
import org.testfx.util.WaitForAsyncUtils;

import javax.imageio.ImageIO;
import java.awt.image.BufferedImage;
import java.io.ByteArrayOutputStream;
import java.util.Base64;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

/** TestFX FxToolkit/FxRobot sarmalayıcısı — MCP tool'larının tek giriş noktası.
 *
 *  Hedef JavaFX uygulaması bu JVM içinde başlatılır (scene graph'a yalnızca
 *  uygulamanın kendi process'inden erişilebilir). FX Application Thread'e
 *  marshalling gerektiren işlemler WaitForAsyncUtils.waitForAsyncFx ile yapılır;
 *  FxRobot etkileşimleri (click/write/push) kendi thread yönetimini kendisi yapar. */
final class FxAutomation {

    /** Agent'a olduğu gibi gösterilecek, beklenen kullanım hataları. */
    static final class ToolError extends RuntimeException {
        ToolError(String message) { super(message); }
    }

    private static final int FX_CALL_TIMEOUT_MS = 10_000;

    private final String defaultAppClass;
    private Application app;
    private FxRobot robot;

    FxAutomation(String defaultAppClass) {
        this.defaultAppClass = defaultAppClass;
    }

    // ---- yaşam döngüsü ----

    synchronized String launch(String appClassName, List<String> args) throws Exception {
        if (app != null) {
            throw new ToolError("Zaten çalışan bir uygulama var (" + app.getClass().getName()
                    + ") — önce close_app çağırın.");
        }
        String className = (appClassName == null || appClassName.isBlank())
                ? defaultAppClass : appClassName;
        if (className == null || className.isBlank()) {
            throw new ToolError("app_class gerekli: javafx.application.Application'ı extend eden "
                    + "sınıfın tam adı (sunucu --app-class ile de başlatılabilir).");
        }
        Class<?> cls;
        try {
            cls = Class.forName(className);
        } catch (ClassNotFoundException e) {
            throw new ToolError("Sınıf classpath'te bulunamadı: " + className
                    + " — sunucuyu `java -cp testfx-mcp.jar:uygulamaniz.jar testfxmcp.Main` "
                    + "şeklinde, uygulama jar'ı classpath'e ekleyerek başlatın.");
        }
        if (!Application.class.isAssignableFrom(cls)) {
            throw new ToolError(className + " javafx.application.Application'ı extend etmiyor.");
        }
        FxToolkit.registerPrimaryStage();
        @SuppressWarnings("unchecked")
        Class<? extends Application> appCls = (Class<? extends Application>) cls;
        app = FxToolkit.setupApplication(appCls, args.toArray(String[]::new));
        robot = new FxRobot();
        WaitForAsyncUtils.waitForFxEvents();
        return "Uygulama başlatıldı: " + className + ". Pencereler:\n" + listWindows();
    }

    synchronized String close() throws Exception {
        if (app == null) return "Çalışan uygulama yok.";
        String name = app.getClass().getName();
        FxToolkit.cleanupApplication(app);
        FxToolkit.cleanupStages();
        app = null;
        robot = null;
        return "Uygulama kapatıldı: " + name;
    }

    private synchronized FxRobot robot() {
        if (robot == null) {
            throw new ToolError("Henüz uygulama başlatılmadı — önce launch_app çağırın.");
        }
        return robot;
    }

    // ---- inceleme ----

    String sceneGraph(int maxDepth) {
        robot();
        return onFxThread(() -> SceneGraphJson.dumpAllWindows(maxDepth));
    }

    String findNodes(String query) {
        FxRobot r = robot();
        return onFxThread(() -> {
            Set<Node> nodes = r.lookup(query).queryAll();
            if (nodes.isEmpty()) {
                throw new ToolError("Eşleşen node yok: \"" + query + "\" — "
                        + "get_scene_graph ile mevcut fx_id/styleClass/metinleri görün.");
            }
            StringBuilder sb = new StringBuilder("[");
            boolean first = true;
            for (Node node : nodes) {
                if (!first) sb.append(',');
                first = false;
                sb.append(SceneGraphJson.nodeSummary(node));
            }
            return sb.append(']').toString();
        });
    }

    String listWindows() {
        return onFxThread(() -> {
            StringBuilder sb = new StringBuilder("[");
            boolean first = true;
            for (Window window : Window.getWindows()) {
                if (!window.isShowing()) continue;
                if (!first) sb.append(',');
                first = false;
                sb.append("{\"type\":\"").append(window.getClass().getSimpleName()).append('"');
                if (window instanceof Stage stage && stage.getTitle() != null) {
                    sb.append(",\"title\":\"").append(stage.getTitle().replace("\"", "\\\"")).append('"');
                }
                sb.append(",\"focused\":").append(window.isFocused());
                sb.append(",\"size\":[").append((int) window.getWidth()).append(',')
                  .append((int) window.getHeight()).append("]}");
            }
            return sb.append(']').toString();
        });
    }

    // ---- etkileşim ----

    String click(String query, String button, int count) {
        FxRobot r = robot();
        requireNode(r, query);
        MouseButton mb = parseButton(button);
        if (count == 2) {
            r.doubleClickOn(query, mb);
        } else {
            r.clickOn(query, mb);
        }
        WaitForAsyncUtils.waitForFxEvents();
        return "Tıklandı: " + query + " (" + mb + (count == 2 ? ", çift tık" : "") + ")";
    }

    String writeText(String query, String text, boolean clear) {
        FxRobot r = robot();
        if (query != null && !query.isBlank()) {
            requireNode(r, query);
            r.clickOn(query);
        }
        if (clear) {
            r.push(KeyCode.SHORTCUT, KeyCode.A);
            r.push(KeyCode.BACK_SPACE);
        }
        r.write(text);
        WaitForAsyncUtils.waitForFxEvents();
        return "Yazıldı: \"" + text + "\"" + (query != null ? " → " + query : "");
    }

    String pressKeys(List<String> keys) {
        FxRobot r = robot();
        KeyCode[] codes = keys.stream().map(FxAutomation::parseKey).toArray(KeyCode[]::new);
        if (codes.length == 0) throw new ToolError("keys boş olamaz.");
        r.push(codes);
        WaitForAsyncUtils.waitForFxEvents();
        return "Basıldı: " + String.join("+", keys);
    }

    String waitFor(String query, long timeoutMs) {
        FxRobot r = robot();
        try {
            WaitForAsyncUtils.waitFor(timeoutMs, TimeUnit.MILLISECONDS, () -> {
                Optional<Node> node = r.lookup(query).tryQuery();
                return node.isPresent() && node.get().isVisible();
            });
        } catch (TimeoutException e) {
            throw new ToolError("Zaman aşımı (" + timeoutMs + " ms): \"" + query
                    + "\" görünür olmadı — get_scene_graph ile durumu kontrol edin.");
        }
        return "Node görünür: " + query;
    }

    // ---- screenshot ----

    /** PNG'yi base64 döndürür. Monocle headless'ta görüntü boş çıkabilir;
     *  güvenilir screenshot için sunucuyu xvfb-run altında çalıştırın. */
    String screenshotBase64(String query) throws Exception {
        FxRobot r = robot();
        Node target;
        if (query != null && !query.isBlank()) {
            target = requireNode(r, query);
        } else {
            target = onFxThread(() -> {
                for (Window window : Window.getWindows()) {
                    if (window.isShowing() && window.getScene() != null) {
                        return window.getScene().getRoot();
                    }
                }
                throw new ToolError("Görünür pencere yok — önce launch_app çağırın.");
            });
        }
        Image image = r.capture(target).getImage();
        BufferedImage buffered = SwingFXUtils.fromFXImage(image, null);
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        ImageIO.write(buffered, "png", out);
        return Base64.getEncoder().encodeToString(out.toByteArray());
    }

    // ---- yardımcılar ----

    private static Node requireNode(FxRobot r, String query) {
        Optional<Node> node = r.lookup(query).tryQuery();
        if (node.isEmpty()) {
            throw new ToolError("Node bulunamadı: \"" + query + "\" — sorgu biçimleri: "
                    + "#fxId, .styleClass, düğme/etiket metni. "
                    + "get_scene_graph ile mevcut node'ları görün.");
        }
        return node.get();
    }

    private static MouseButton parseButton(String button) {
        if (button == null || button.isBlank()) return MouseButton.PRIMARY;
        try {
            return MouseButton.valueOf(button.toUpperCase(Locale.ROOT));
        } catch (IllegalArgumentException e) {
            throw new ToolError("Geçersiz button: " + button
                    + " — geçerli değerler: PRIMARY, SECONDARY, MIDDLE.");
        }
    }

    private static final Map<String, KeyCode> KEY_ALIASES = Map.of(
            "CTRL", KeyCode.CONTROL,
            "ESC", KeyCode.ESCAPE,
            "DEL", KeyCode.DELETE,
            "RETURN", KeyCode.ENTER,
            "CMD", KeyCode.META,
            "WIN", KeyCode.WINDOWS,
            "PGUP", KeyCode.PAGE_UP,
            "PGDN", KeyCode.PAGE_DOWN);

    private static KeyCode parseKey(String key) {
        String normalized = key.trim().toUpperCase(Locale.ROOT).replace(' ', '_');
        KeyCode alias = KEY_ALIASES.get(normalized);
        if (alias != null) return alias;
        try {
            return KeyCode.valueOf(normalized);
        } catch (IllegalArgumentException e) {
            throw new ToolError("Geçersiz tuş: " + key
                    + " — javafx.scene.input.KeyCode adları kullanın (örn. ENTER, TAB, F5, CTRL, A).");
        }
    }

    /** İşi FX Application Thread'de çalıştırır, sonucu bekler.
     *  ToolError'ları sarmalamadan geçirir. */
    private <T> T onFxThread(java.util.concurrent.Callable<T> job) {
        try {
            return WaitForAsyncUtils.waitForAsyncFx(FX_CALL_TIMEOUT_MS, job);
        } catch (RuntimeException e) {
            for (Throwable t = e; t != null; t = t.getCause()) {
                if (t instanceof ToolError toolError) throw toolError;
            }
            throw e;
        }
    }
}
