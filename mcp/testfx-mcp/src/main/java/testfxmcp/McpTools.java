package testfxmcp;

import io.modelcontextprotocol.json.McpJsonMapper;
import io.modelcontextprotocol.server.McpServerFeatures.SyncToolSpecification;
import io.modelcontextprotocol.spec.McpSchema.CallToolResult;
import io.modelcontextprotocol.spec.McpSchema.ImageContent;
import io.modelcontextprotocol.spec.McpSchema.Tool;

import java.util.List;
import java.util.Map;

/** MCP tool tanımları + handler'ları. Tüm gerçek iş FxAutomation'dadır;
 *  burada yalnızca şema, parametre çözümleme ve hata → isError çevrimi var. */
final class McpTools {

    private McpTools() { }

    /** Tool handler gövdesi: başarı metni döndürür, hatada exception fırlatır. */
    @FunctionalInterface
    private interface Handler {
        CallToolResult run(Map<String, Object> args) throws Exception;
    }

    static List<SyncToolSpecification> all(McpJsonMapper mapper, FxAutomation fx) {
        return List.of(
            spec(mapper, "launch_app",
                "JavaFX uygulamasını bu JVM içinde başlatır. app_class: "
                    + "javafx.application.Application'ı extend eden sınıfın tam adı "
                    + "(sunucu --app-class ile başlatıldıysa boş bırakılabilir). "
                    + "Uygulama jar'ı sunucunun classpath'inde olmalıdır.",
                """
                {"type":"object","properties":{
                  "app_class":{"type":"string","description":"Application alt sınıfının tam adı (örn. com.ornek.UygulamaFX)"},
                  "args":{"type":"array","items":{"type":"string"},"description":"Uygulama argümanları"}
                }}""",
                args -> text(fx.launch(str(args, "app_class"), strList(args, "args")))),

            spec(mapper, "close_app",
                "Çalışan JavaFX uygulamasını ve tüm pencerelerini kapatır.",
                "{\"type\":\"object\",\"properties\":{}}",
                args -> text(fx.close())),

            spec(mapper, "get_scene_graph",
                "Açık tüm pencerelerin scene graph'ını (JavaFX'in DOM karşılığı) JSON "
                    + "olarak döndürür: node tipi, fx_id, styleClass, metin, görünürlük, "
                    + "bounds. Etkileşimden önce doğru sorguyu bulmak için kullanın.",
                """
                {"type":"object","properties":{
                  "max_depth":{"type":"integer","description":"Maksimum ağaç derinliği (varsayılan 25)"}
                }}""",
                args -> text(fx.sceneGraph(intOr(args, "max_depth", 25)))),

            spec(mapper, "find_nodes",
                "TestFX sorgusuyla eşleşen node'ları listeler. Sorgu biçimleri: "
                    + "#fxId, .styleClass veya düğme/etiket metni (örn. \"Kaydet\").",
                """
                {"type":"object","properties":{
                  "query":{"type":"string","description":"TestFX sorgusu: #fxId, .styleClass veya metin"}
                },"required":["query"]}""",
                args -> text(fx.findNodes(require(args, "query")))),

            spec(mapper, "click",
                "Sorguyla eşleşen node'a tıklar.",
                """
                {"type":"object","properties":{
                  "query":{"type":"string","description":"TestFX sorgusu: #fxId, .styleClass veya metin"},
                  "button":{"type":"string","enum":["PRIMARY","SECONDARY","MIDDLE"],"description":"Fare tuşu (varsayılan PRIMARY; SECONDARY = sağ tık)"},
                  "count":{"type":"integer","enum":[1,2],"description":"1 = tek tık (varsayılan), 2 = çift tık"}
                },"required":["query"]}""",
                args -> text(fx.click(require(args, "query"),
                        str(args, "button"), intOr(args, "count", 1)))),

            spec(mapper, "write_text",
                "Metin yazar. query verilirse önce o alana tıklar; "
                    + "clear=true mevcut içeriği önce siler.",
                """
                {"type":"object","properties":{
                  "text":{"type":"string","description":"Yazılacak metin"},
                  "query":{"type":"string","description":"Hedef alan sorgusu (örn. #kullaniciAdi); boşsa odaktaki alana yazar"},
                  "clear":{"type":"boolean","description":"true ise alanın mevcut içeriğini önce siler"}
                },"required":["text"]}""",
                args -> text(fx.writeText(str(args, "query"), require(args, "text"),
                        boolOr(args, "clear", false)))),

            spec(mapper, "press_keys",
                "Tuş kombinasyonuna basar (hepsi basılı tutulup bırakılır). "
                    + "Örn. [\"CTRL\",\"S\"] veya [\"ENTER\"].",
                """
                {"type":"object","properties":{
                  "keys":{"type":"array","items":{"type":"string"},"description":"KeyCode adları: ENTER, TAB, ESC, F5, CTRL, ALT, SHIFT, A..Z"}
                },"required":["keys"]}""",
                args -> text(fx.pressKeys(strList(args, "keys")))),

            spec(mapper, "wait_for",
                "Sorguyla eşleşen bir node görünür olana dek bekler "
                    + "(asenkron UI güncellemeleri için).",
                """
                {"type":"object","properties":{
                  "query":{"type":"string","description":"TestFX sorgusu: #fxId, .styleClass veya metin"},
                  "timeout_ms":{"type":"integer","description":"Zaman aşımı, milisaniye (varsayılan 5000)"}
                },"required":["query"]}""",
                args -> text(fx.waitFor(require(args, "query"),
                        intOr(args, "timeout_ms", 5000)))),

            spec(mapper, "screenshot",
                "Ekran görüntüsü alır (PNG). query verilirse o node'u, verilmezse ilk "
                    + "görünür pencereyi yakalar. Not: Monocle headless kipinde görüntü "
                    + "boş çıkabilir; güvenilir screenshot için sunucuyu xvfb-run altında "
                    + "çalıştırın.",
                """
                {"type":"object","properties":{
                  "query":{"type":"string","description":"Yakalanacak node sorgusu; boşsa tüm pencere"}
                }}""",
                args -> CallToolResult.builder()
                        .addContent(new ImageContent(null,
                                fx.screenshotBase64(str(args, "query")), "image/png"))
                        .build()),

            spec(mapper, "list_windows",
                "Açık pencereleri (stage) başlık, odak ve boyut bilgisiyle listeler.",
                "{\"type\":\"object\",\"properties\":{}}",
                args -> text(fx.listWindows()))
        );
    }

    private static SyncToolSpecification spec(McpJsonMapper mapper, String name,
                                              String description, String schemaJson,
                                              Handler handler) {
        Tool tool = Tool.builder()
                .name(name)
                .description(description)
                .inputSchema(mapper, schemaJson)
                .build();
        return SyncToolSpecification.builder()
                .tool(tool)
                .callHandler((exchange, request) -> {
                    try {
                        Map<String, Object> args = request.arguments() == null
                                ? Map.of() : request.arguments();
                        return handler.run(args);
                    } catch (FxAutomation.ToolError e) {
                        return error(e.getMessage());
                    } catch (Exception e) {
                        return error(e.getClass().getSimpleName() + ": " + e.getMessage());
                    }
                })
                .build();
    }

    private static CallToolResult text(String message) {
        return CallToolResult.builder().addTextContent(message).build();
    }

    private static CallToolResult error(String message) {
        return CallToolResult.builder().isError(true).addTextContent(message).build();
    }

    // ---- parametre çözümleme ----

    private static String str(Map<String, Object> args, String key) {
        Object v = args.get(key);
        return v == null ? null : v.toString();
    }

    private static String require(Map<String, Object> args, String key) {
        String v = str(args, key);
        if (v == null || v.isBlank()) {
            throw new FxAutomation.ToolError("Zorunlu parametre eksik: " + key);
        }
        return v;
    }

    private static int intOr(Map<String, Object> args, String key, int fallback) {
        Object v = args.get(key);
        if (v == null) return fallback;
        if (v instanceof Number n) return n.intValue();
        try {
            return Integer.parseInt(v.toString());
        } catch (NumberFormatException e) {
            throw new FxAutomation.ToolError("Sayı bekleniyordu: " + key + "=" + v);
        }
    }

    private static boolean boolOr(Map<String, Object> args, String key, boolean fallback) {
        Object v = args.get(key);
        if (v == null) return fallback;
        if (v instanceof Boolean b) return b;
        return Boolean.parseBoolean(v.toString());
    }

    @SuppressWarnings("unchecked")
    private static List<String> strList(Map<String, Object> args, String key) {
        Object v = args.get(key);
        if (v == null) return List.of();
        if (v instanceof List<?> list) {
            return list.stream().map(Object::toString).toList();
        }
        throw new FxAutomation.ToolError("Liste bekleniyordu: " + key + "=" + v);
    }
}
