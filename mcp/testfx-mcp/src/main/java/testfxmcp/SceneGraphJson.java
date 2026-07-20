package testfxmcp;

import javafx.collections.ObservableList;
import javafx.geometry.Bounds;
import javafx.scene.Node;
import javafx.scene.Parent;
import javafx.scene.Scene;
import javafx.scene.control.Labeled;
import javafx.scene.control.TextInputControl;
import javafx.stage.Stage;
import javafx.stage.Window;

/** Scene graph → JSON dökümü (examples/java-templates/SceneGraphDumper.java'dan
 *  uyarlandı: dosya yerine String üretir, derinlik limiti eklendi).
 *
 *  KRİTİK: Bu sınıfın metotları yalnızca FX Application Thread üzerinden
 *  çağrılmalıdır — marshalling çağıranın sorumluluğudur (FxAutomation yapar). */
final class SceneGraphJson {

    private SceneGraphJson() { }

    /** Açık tüm pencerelerin scene graph'ını JSON dizisi olarak döndürür. */
    static String dumpAllWindows(int maxDepth) {
        StringBuilder sb = new StringBuilder();
        sb.append('[');
        boolean first = true;
        for (Window window : Window.getWindows()) {
            if (!window.isShowing()) continue;
            if (!first) sb.append(',');
            first = false;
            sb.append("{\"window\":\"")
              .append(window.getClass().getSimpleName()).append('"');
            if (window instanceof Stage stage && stage.getTitle() != null) {
                sb.append(",\"title\":\"").append(escape(stage.getTitle())).append('"');
            }
            sb.append(",\"focused\":").append(window.isFocused());
            sb.append(",\"root\":");
            Scene scene = window.getScene();
            if (scene != null && scene.getRoot() != null) {
                appendNode(sb, scene.getRoot(), maxDepth);
            } else {
                sb.append("null");
            }
            sb.append('}');
        }
        sb.append(']');
        return sb.toString();
    }

    /** Tek bir node'un çocuksuz özet JSON'u (find_nodes çıktısı için). */
    static String nodeSummary(Node node) {
        StringBuilder sb = new StringBuilder();
        appendNode(sb, node, 0);
        return sb.toString();
    }

    private static void appendNode(StringBuilder sb, Node node, int remainingDepth) {
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
                if (remainingDepth <= 0) {
                    sb.append(",\"children_truncated\":").append(children.size());
                } else {
                    sb.append(",\"children\":[");
                    for (int i = 0; i < children.size(); i++) {
                        if (i > 0) sb.append(',');
                        appendNode(sb, children.get(i), remainingDepth - 1);
                    }
                    sb.append(']');
                }
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
        StringBuilder sb = new StringBuilder(s.length() + 8);
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            switch (c) {
                case '\\' -> sb.append("\\\\");
                case '"' -> sb.append("\\\"");
                case '\n' -> sb.append("\\n");
                case '\r' -> sb.append("\\r");
                case '\t' -> sb.append("\\t");
                default -> {
                    if (c < 0x20) sb.append(String.format("\\u%04x", (int) c));
                    else sb.append(c);
                }
            }
        }
        return sb.toString();
    }
}
