package testfxmcp.demo;

import javafx.application.Application;
import javafx.geometry.Insets;
import javafx.scene.Scene;
import javafx.scene.control.Button;
import javafx.scene.control.Label;
import javafx.scene.control.TextField;
import javafx.scene.layout.VBox;
import javafx.stage.Stage;

/** Sunucuyu kendi uygulamanız olmadan denemek için mini JavaFX uygulaması.
 *
 *    java -cp testfx-mcp.jar testfxmcp.Main --app-class testfxmcp.demo.DemoApp
 *
 *  launch_app → write_text(#nameField, "Dünya") → click(#greetButton) →
 *  wait_for("Merhaba, Dünya!") akışıyla uçtan uca test edilebilir. */
public class DemoApp extends Application {

    @Override
    public void start(Stage stage) {
        TextField nameField = new TextField();
        nameField.setId("nameField");
        nameField.setPromptText("Adınız");

        Label greetingLabel = new Label("");
        greetingLabel.setId("greetingLabel");

        Button greetButton = new Button("Selamla");
        greetButton.setId("greetButton");
        greetButton.setOnAction(e ->
                greetingLabel.setText("Merhaba, " + nameField.getText() + "!"));

        VBox root = new VBox(10, nameField, greetButton, greetingLabel);
        root.setPadding(new Insets(16));

        stage.setTitle("TestFX MCP Demo");
        stage.setScene(new Scene(root, 320, 160));
        stage.show();
    }

    public static void main(String[] args) {
        launch(args);
    }
}
