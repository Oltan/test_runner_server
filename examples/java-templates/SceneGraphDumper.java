// ŞABLON — TestFX projenize kopyalayıp uyarlayın.
// JavaFX'in DOM karşılığı scene graph'tır ve test process'i içinden tam
// erişilebilir — MCP veya dış araç gerekmez. Test FAIL olduğunda bu dump +
// screenshot, healing pipeline'ının JavaFX girdisidir.
//
// KRİTİK: Scene graph'a yalnızca FX Application Thread üzerinden dokunulabilir.
// Bu sınıf dump'ı Platform.runLater + CountDownLatch ile o thread'de yapar.
// TestFX testinde kullanım (ör. JUnit 5):
//
//   @AfterEach
//   void captureOnFailure(TestInfo info) {
//       if (testFailed) {  // kendi fail-takip mekanizmanıza göre
//           SceneGraphDumper.dumpAllWindows(
//               Path.of("target", "failure-artifacts",
//                       info.getDisplayName(), "scenegraph.json"));
//       }
//   }
//
// Screenshot notu: Monocle headless'ta ekran görüntüsü boş çıkabilir;
// güvenilir screenshot için testleri `xvfb-run -a mvn test` ile koşun ve
// robot.capture(...) veya Scene.snapshot(...) kullanın.

package hooks; // kendi paketinize göre değiştirin

import javafx.application.Platform;
import javafx.collections.ObservableList;
import javafx.geometry.Bounds;
import javafx.scene.Node;
import javafx.scene.Parent;
import javafx.scene.Scene;
import javafx.scene.control.Labeled;
import javafx.scene.control.TextInputControl;
import javafx.stage.Window;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

public final class SceneGraphDumper {

    private SceneGraphDumper() { }

    /** Açık tüm pencerelerin scene graph'ını JSON olarak dosyaya yazar.
     *  Savunmacıdır: hata durumunda sessizce vazgeçer, testi asla bozmaz. */
    public static void dumpAllWindows(Path outFile) {
        try {
            StringBuilder sb = new StringBuilder();
            CountDownLatch latch = new CountDownLatch(1);
            Runnable job = () -> {
                try {
                    sb.append('[');
                    boolean first = true;
                    for (Window window : Window.getWindows()) {
                        if (!window.isShowing()) continue;
                        if (!first) sb.append(',');
                        first = false;
                        sb.append("{\"window\":\"")
                          .append(window.getClass().getSimpleName())
                          .append("\",\"root\":");
                        Scene scene = window.getScene();
                        if (scene != null && scene.getRoot() != null) {
                            appendNode(sb, scene.getRoot());
                        } else {
                            sb.append("null");
                        }
                        sb.append('}');
                    }
                    sb.append(']');
                } finally {
                    latch.countDown();
                }
            };
            if (Platform.isFxApplicationThread()) {
                job.run();
            } else {
                Platform.runLater(job);
                if (!latch.await(10, TimeUnit.SECONDS)) return;
            }
            Files.createDirectories(outFile.getParent());
            Files.writeString(outFile, sb.toString(), StandardCharsets.UTF_8);
        } catch (Exception ignored) { }
    }

    private static void appendNode(StringBuilder sb, Node node) {
        sb.append("{\"type\":\"").append(node.getClass().getSimpleName()).append('"');
        if (node.getId() != null) {
            sb.append(",\"fx_id\":\"").append(escape(node.getId())).append('"');
        }
        if (!node.getStyleClass().isEmpty()) {
            sb.append(",\"styleClass\":\"")
              .append(escape(String.join(" ", node.getStyleClass()))).append('"');
        }
        String text = textOf(node);
        if (text != null && !text.isEmpty()) {
            sb.append(",\"text\":\"").append(escape(text)).append('"');
        }
        sb.append(",\"visible\":").append(node.isVisible());
        sb.append(",\"disabled\":").append(node.isDisabled());
        Bounds b = node.getBoundsInParent();
        sb.append(",\"bounds\":[").append((int) b.getMinX()).append(',')
          .append((int) b.getMinY()).append(',')
          .append((int) b.getWidth()).append(',')
          .append((int) b.getHeight()).append(']');
        if (node instanceof Parent parent) {
            ObservableList<Node> children = parent.getChildrenUnmodifiable();
            if (!children.isEmpty()) {
                sb.append(",\"children\":[");
                for (int i = 0; i < children.size(); i++) {
                    if (i > 0) sb.append(',');
                    appendNode(sb, children.get(i));
                }
                sb.append(']');
            }
        }
        sb.append('}');
    }

    private static String textOf(Node node) {
        if (node instanceof Labeled labeled) return labeled.getText();
        if (node instanceof TextInputControl input) return input.getText();
        return null;
    }

    private static String escape(String s) {
        return s.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n");
    }
}
