#!/bin/bash
# Healing'i GERÇEK PROJENİZE DOKUNMADAN test etmek için iki sahte "Java"
# projesi (git repo) oluşturur:
#   heal-fixture-a → locator kırılması (Mod A testi)
#   heal-fixture-b → assertion hatası + sahte agent (Mod B testi)
#
# Kullanım:  bash examples/heal-fixtures/create.sh [hedef-dizin]
#            (varsayılan hedef: /tmp/heal-fixtures)
# Sonda projects.yaml'a yapıştırılacak hazır blok basılır.
set -e
DEST="${1:-/tmp/heal-fixtures}"
mkdir -p "$DEST"
DEST="$(cd "$DEST" && pwd)"

# ---------- Fixture A: locator kırılması (Mod A) ----------
rm -rf "$DEST/heal-fixture-a"
mkdir -p "$DEST/heal-fixture-a/pages"
cd "$DEST/heal-fixture-a"
git init -q

cat > pages/OrderPage.java <<'EOF'
public class OrderPage {
    // POM: sipariş gönderme butonu — uygulamada id değişti, bu locator KIRIK
    private final By submitButton = By.xpath("//button[@id='submit-btn']");
}
EOF

cat > check.py <<'EOF'
#!/usr/bin/env python3
"""Sahte 'mvn test': koddaki locator uygulamanin YENI DOM'unda var mi?"""
import json, sys
from pathlib import Path

code = Path("pages/OrderPage.java").read_text(encoding="utf-8")
ok = "submit-button-v2" in code  # uygulamadaki yeni id

target = Path("target"); target.mkdir(exist_ok=True)
error = ("org.openqa.selenium.NoSuchElementException: "
         "Unable to locate element: "
         "{\"method\":\"xpath\",\"selector\":\"//button[@id='submit-btn']\"}")
step = {"keyword": "When ", "name": "siparisi gonderir",
        "result": {"status": "passed" if ok else "failed",
                   "duration": 100000000}}
if not ok:
    step["result"]["error_message"] = error
    art = target / "failure-artifacts" / "Siparis_gonderilir"
    art.mkdir(parents=True, exist_ok=True)
    (art / "tab_0.html").write_text(
        "<html><body><form id='order-form'>"
        "<input id='order-note' name='note'/>"
        "<button id='submit-button-v2' class='btn primary' type='submit'>"
        "Gonder</button>"
        "<button id='cancel-btn' class='btn'>Vazgec</button>"
        "</form></body></html>", encoding="utf-8")
    (art / "meta.json").write_text(json.dumps(
        {"scenario": "Siparis gonderilir",
         "tabs": [{"active": "true", "url": "http://app/order"}]}))
json.dump([{"uri": "features/order.feature", "name": "Siparis",
            "elements": [{"type": "scenario", "name": "Siparis gonderilir",
                          "steps": [step]}]}],
          open(target / "cucumber-report.json", "w"), ensure_ascii=False)
print("SONUC:", "PASSED" if ok else "FAILED", flush=True)
sys.exit(0 if ok else 1)
EOF

echo "target/" > .gitignore
git add -A
git -c user.name=fixture -c user.email=f@local commit -qm "heal fixture a"

# ---------- Fixture B: assertion hatası (Mod B) ----------
rm -rf "$DEST/heal-fixture-b"
mkdir -p "$DEST/heal-fixture-b/steps"
cd "$DEST/heal-fixture-b"
git init -q

cat > steps/CartSteps.java <<'EOF'
public class CartSteps {
    // Kampanya sonrasi sepette beklenen urun sayisi — uygulama artik 3 donduruyor
    private static final int EXPECTED_ITEMS = 5;
}
EOF

cat > check.py <<'EOF'
#!/usr/bin/env python3
"""Sahte 'mvn test': uygulama 3 donduruyor; kod 5 bekliyorsa FAIL."""
import json, sys
from pathlib import Path

code = Path("steps/CartSteps.java").read_text(encoding="utf-8")
ok = "EXPECTED_ITEMS = 3" in code
target = Path("target"); target.mkdir(exist_ok=True)
step = {"keyword": "Then ", "name": "sepette urun sayisi dogrulanir",
        "result": {"status": "passed" if ok else "failed",
                   "duration": 100000000}}
if not ok:
    step["result"]["error_message"] = \
        "java.lang.AssertionError: expected:<5> but was:<3>"
json.dump([{"uri": "features/cart.feature", "name": "Sepet",
            "elements": [{"type": "scenario", "name": "Kampanya sepeti",
                          "steps": [step]}]}],
          open(target / "cucumber-report.json", "w"), ensure_ascii=False)
print("SONUC:", "PASSED" if ok else "FAILED", flush=True)
sys.exit(0 if ok else 1)
EOF

cat > fake_agent.py <<'EOF'
#!/usr/bin/env python3
"""opencode'u taklit eden sahte agent: gorev dosyasini okur, kodu duzeltir.
Gercek agent'inizi baglamadan once Mod B akisini bununla dogrulayin."""
import os
from pathlib import Path

task = Path(os.environ["HEAL_PROMPT_FILE"]).read_text(encoding="utf-8")
assert "Kampanya sepeti" in task, "gorev dosyasinda senaryo yok"

path = Path("steps/CartSteps.java")
path.write_text(path.read_text(encoding="utf-8")
                .replace("EXPECTED_ITEMS = 5", "EXPECTED_ITEMS = 3"),
                encoding="utf-8")
print("fake agent: EXPECTED_ITEMS 5 -> 3 duzeltildi")
EOF

echo "target/" > .gitignore
git add -A
git -c user.name=fixture -c user.email=f@local commit -qm "heal fixture b"

cat <<YAML

Fixture'lar hazir: $DEST

================================================================
projects.yaml'a asagidaki blogu ekleyin, sonra servisi yeniden
baslatin. Mock LLM icin once calistirin:
  python3 examples/heal-fixtures/mock_llm.py &
Gercek vLLM'e gecerken base_url ve model'i degistirmeniz yeterli.
================================================================

  - id: heal-a
    name: "Heal Testi A (locator / Mod A)"
    path: $DEST/heal-fixture-a
    command: "{python} check.py"
    results:
      cucumber_json: target/cucumber-report.json
    agent:
      llm:
        base_url: "http://127.0.0.1:8199/v1"   # mock; vLLM'de degistirin
        model: "mock-model"                     # vLLM'de: qwen3.6-35b-a3b
      scenario_command: "{python} check.py"
      edit_whitelist:
        - pages/

  - id: heal-b
    name: "Heal Testi B (assertion / Mod B)"
    path: $DEST/heal-fixture-b
    command: "{python} check.py"
    results:
      cucumber_json: target/cucumber-report.json
    agent:
      agent_command: "{python} fake_agent.py"    # sonra: opencode/aider komutu
      agent_model: "mock-agent"                 # sonra: glm-5.2-fp8
      scenario_command: "{python} check.py"
      edit_whitelist:
        - steps/
YAML
