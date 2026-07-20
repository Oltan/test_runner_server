package testfxmcp;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** Uçtan uca duman testi: DemoApp'ı headless başlat, scene graph'ı doğrula,
 *  etkileşim kur, sonucu bekle.
 *
 *  Varsayılan Monocle headless'tır; gerçek ekranda koşmak için
 *  TESTFX_HEADED=1 ile çalıştırın (veya xvfb-run altında koşun). */
class SmokeTest {

    static {
        if (System.getenv("TESTFX_HEADED") == null) {
            System.setProperty("testfx.robot", "glass");
            System.setProperty("testfx.headless", "true");
            System.setProperty("glass.platform", "Monocle");
            System.setProperty("monocle.platform", "Headless");
            System.setProperty("prism.order", "sw");
            System.setProperty("java.awt.headless", "true");
        }
    }

    private final FxAutomation fx = new FxAutomation(null);

    @AfterEach
    void tearDown() throws Exception {
        fx.close();
    }

    @Test
    void launchInspectInteract() throws Exception {
        String launched = fx.launch("testfxmcp.demo.DemoApp", List.of());
        assertTrue(launched.contains("DemoApp"), launched);

        String graph = fx.sceneGraph(25);
        assertTrue(graph.contains("\"fx_id\":\"nameField\""), graph);
        assertTrue(graph.contains("\"fx_id\":\"greetButton\""), graph);

        String found = fx.findNodes("#greetButton");
        assertTrue(found.contains("\"text\":\"Selamla\""), found);

        fx.writeText("#nameField", "Dünya", false);
        fx.click("#greetButton", null, 1);
        fx.waitFor("Merhaba, Dünya!", 3000);

        String windows = fx.listWindows();
        assertTrue(windows.contains("TestFX MCP Demo"), windows);
    }

    @Test
    void clearRewritesFieldContent() throws Exception {
        fx.launch("testfxmcp.demo.DemoApp", List.of());
        fx.writeText("#nameField", "eski", false);
        fx.writeText("#nameField", "yeni", true);
        fx.click("#greetButton", null, 1);
        fx.waitFor("Merhaba, yeni!", 3000);
    }

    @Test
    void usefulErrorsForAgent() throws Exception {
        FxAutomation.ToolError beforeLaunch = assertThrows(FxAutomation.ToolError.class,
                () -> fx.click("#yok", null, 1));
        assertTrue(beforeLaunch.getMessage().contains("launch_app"), beforeLaunch.getMessage());

        fx.launch("testfxmcp.demo.DemoApp", List.of());

        FxAutomation.ToolError missingNode = assertThrows(FxAutomation.ToolError.class,
                () -> fx.click("#boyleBirNodeYok", null, 1));
        assertTrue(missingNode.getMessage().contains("get_scene_graph"), missingNode.getMessage());

        FxAutomation.ToolError timeout = assertThrows(FxAutomation.ToolError.class,
                () -> fx.waitFor("#asla", 300));
        assertTrue(timeout.getMessage().contains("Zaman aşımı"), timeout.getMessage());

        FxAutomation.ToolError doubleLaunch = assertThrows(FxAutomation.ToolError.class,
                () -> fx.launch("testfxmcp.demo.DemoApp", List.of()));
        assertTrue(doubleLaunch.getMessage().contains("close_app"), doubleLaunch.getMessage());

        assertEquals("Uygulama kapatıldı: testfxmcp.demo.DemoApp", fx.close());
    }
}
