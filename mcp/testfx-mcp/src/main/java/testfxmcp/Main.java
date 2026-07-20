package testfxmcp;

import io.modelcontextprotocol.json.McpJsonDefaults;
import io.modelcontextprotocol.json.McpJsonMapper;
import io.modelcontextprotocol.server.McpServer;
import io.modelcontextprotocol.server.McpSyncServer;
import io.modelcontextprotocol.server.transport.StdioServerTransportProvider;
import io.modelcontextprotocol.spec.McpSchema.ServerCapabilities;

import java.util.ArrayList;
import java.util.List;

/** TestFX MCP Server giriş noktası — stdio üzerinden MCP (JSON-RPC) konuşur.
 *
 *  Kullanım:
 *    java -cp testfx-mcp.jar:uygulamaniz.jar testfxmcp.Main [seçenekler]
 *
 *  Seçenekler:
 *    --app-class <FQN>   Varsayılan Application sınıfı (launch_app parametresiz çağrılabilir)
 *    --app-args "a b"    Varsayılan uygulama argümanları
 *    --headless          Monocle headless kipi (xvfb yoksa; screenshot boş çıkabilir)
 *
 *  KRİTİK: stdout MCP transport'una aittir — tüm loglar stderr'e gider. */
public final class Main {

    static final String VERSION = "0.1.0";

    private Main() { }

    public static void main(String[] args) throws Exception {
        String appClass = null;
        List<String> appArgs = new ArrayList<>();
        boolean headless = false;

        for (int i = 0; i < args.length; i++) {
            switch (args[i]) {
                case "--app-class" -> appClass = requireValue(args, ++i, "--app-class");
                case "--app-args" -> {
                    for (String part : requireValue(args, ++i, "--app-args").split("\\s+")) {
                        if (!part.isBlank()) appArgs.add(part);
                    }
                }
                case "--headless" -> headless = true;
                case "--help", "-h" -> {
                    System.err.println("Kullanım: java -cp testfx-mcp.jar:app.jar testfxmcp.Main "
                            + "[--app-class FQN] [--app-args \"...\"] [--headless]");
                    return;
                }
                default -> {
                    System.err.println("Bilinmeyen seçenek: " + args[i] + " (--help)");
                    System.exit(2);
                }
            }
        }

        // slf4j-simple varsayılan olarak stderr'e yazar; garantiye alıyoruz.
        System.setProperty("org.slf4j.simpleLogger.logFile", "System.err");

        if (headless) {
            // JavaFX yüklenmeden ÖNCE set edilmeli.
            System.setProperty("testfx.robot", "glass");
            System.setProperty("testfx.headless", "true");
            System.setProperty("glass.platform", "Monocle");
            System.setProperty("monocle.platform", "Headless");
            System.setProperty("prism.order", "sw");
            System.setProperty("java.awt.headless", "true");
        }

        FxAutomation fx = new FxAutomation(appClass);
        McpJsonMapper mapper = McpJsonDefaults.getMapper();

        McpSyncServer server = McpServer.sync(new StdioServerTransportProvider(mapper))
                .serverInfo("testfx-mcp", VERSION)
                .capabilities(ServerCapabilities.builder().tools(true).build())
                .instructions("JavaFX uygulamalarını TestFX ile süren otomasyon sunucusu. "
                        + "Akış: launch_app → get_scene_graph (sorguları öğren) → "
                        + "click/write_text/press_keys → wait_for → screenshot. "
                        + "Sorgu biçimleri: #fxId, .styleClass veya görünen metin.")
                .tools(McpTools.all(mapper, fx))
                .build();

        System.err.println("[testfx-mcp] hazır (stdio) — appClass="
                + (appClass == null ? "-" : appClass) + " headless=" + headless);

        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            try {
                fx.close();
            } catch (Exception ignored) { }
            server.closeGracefully();
        }));

        // stdio oturumu arka plan thread'lerinde yaşar; ana thread'i canlı tut.
        Thread.currentThread().join();
    }

    private static String requireValue(String[] args, int index, String flag) {
        if (index >= args.length) {
            System.err.println(flag + " bir değer bekliyor");
            System.exit(2);
        }
        return args[index];
    }
}
