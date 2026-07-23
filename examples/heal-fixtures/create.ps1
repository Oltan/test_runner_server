# create.sh'ın Windows PowerShell karşılığı.
# Healing'i gerçek projenize dokunmadan test etmek için iki sahte "Java"
# projesi (git repo) oluşturur. İkisi de coding agent (opencode/Claude Code)
# üzerinden düzeltilir — sahte agent'lar gerçek CLI'nızı taklit eder.
#
# Kullanım:  powershell -ExecutionPolicy Bypass -File examples\heal-fixtures\create.ps1 [hedef-dizin]
#            (varsayılan hedef: $env:TEMP\heal-fixtures)
param([string]$Dest = "$env:TEMP\heal-fixtures")

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $Dest | Out-Null
$Dest = (Resolve-Path $Dest).Path

# ---------- Fixture A: locator kırılması ----------
$A = Join-Path $Dest "heal-fixture-a"
if (Test-Path $A) { Remove-Item -Recurse -Force $A }
New-Item -ItemType Directory -Force -Path "$A\pages" | Out-Null
Set-Location $A
git init -q

@'
public class OrderPage {
    // POM: siparis gonderme butonu - uygulamada id degisti, bu locator KIRIK
    private final By submitButton = By.xpath("//button[@id='submit-btn']");
}
'@ | Set-Content -Encoding UTF8 "pages\OrderPage.java"

@'
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
'@ | Set-Content -Encoding UTF8 "check.py"

@'
#!/usr/bin/env python3
"""opencode/Claude Code'u taklit eden sahte agent: gorev dosyasini okur,
kodu kendisi duzeltir. Gercek agent'inizi baglamadan once akisi bununla
dogrulayin (bkz. KILAVUZ.md 7.1)."""
import os
from pathlib import Path

task = Path(os.environ["HEAL_PROMPT_FILE"]).read_text(encoding="utf-8")
assert "siparisi gonderir" in task or "Siparis" in task, \
    "gorev dosyasinda senaryo yok"

path = Path("pages/OrderPage.java")
path.write_text(path.read_text(encoding="utf-8")
                .replace("submit-btn", "submit-button-v2"),
                encoding="utf-8")
print("fake agent: locator submit-btn -> submit-button-v2 duzeltildi")
'@ | Set-Content -Encoding UTF8 "fake_agent.py"

"target/" | Set-Content ".gitignore"
git add -A
git -c user.name=fixture -c user.email=f@local commit -qm "heal fixture a"

# ---------- Fixture B: assertion hatası ----------
$B = Join-Path $Dest "heal-fixture-b"
if (Test-Path $B) { Remove-Item -Recurse -Force $B }
New-Item -ItemType Directory -Force -Path "$B\steps" | Out-Null
Set-Location $B
git init -q

@'
public class CartSteps {
    // Kampanya sonrasi sepette beklenen urun sayisi - uygulama artik 3 donduruyor
    private static final int EXPECTED_ITEMS = 5;
}
'@ | Set-Content -Encoding UTF8 "steps\CartSteps.java"

@'
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
'@ | Set-Content -Encoding UTF8 "check.py"

@'
#!/usr/bin/env python3
"""opencode/Claude Code'u taklit eden sahte agent: gorev dosyasini okur,
kodu kendisi duzeltir. Gercek agent'inizi baglamadan once akisi bununla
dogrulayin (bkz. KILAVUZ.md 7.1)."""
import os
from pathlib import Path

task = Path(os.environ["HEAL_PROMPT_FILE"]).read_text(encoding="utf-8")
assert "Kampanya sepeti" in task, "gorev dosyasinda senaryo yok"

path = Path("steps/CartSteps.java")
path.write_text(path.read_text(encoding="utf-8")
                .replace("EXPECTED_ITEMS = 5", "EXPECTED_ITEMS = 3"),
                encoding="utf-8")
print("fake agent: EXPECTED_ITEMS 5 -> 3 duzeltildi")
'@ | Set-Content -Encoding UTF8 "fake_agent.py"

"target/" | Set-Content ".gitignore"
git add -A
git -c user.name=fixture -c user.email=f@local commit -qm "heal fixture b"

$DestYaml = $Dest -replace '\\', '/'
@"

Fixture'lar hazir: $Dest

================================================================
projects.yaml'a asagidaki blogu ekleyin, sonra sunucuyu yeniden
baslatin. Ikisi de sahte "agent" ile calisir (gercek opencode/claude
kurulu olmasa da akisi uctan uca gorursunuz). Gercek CLI'niza gecerken
sadece agent_command satirini kaldirip agent_cli: opencode (veya
claude-code) yazmaniz yeterli.
================================================================

  - id: heal-a
    name: "Heal Testi A (locator kirilmasi)"
    path: $DestYaml/heal-fixture-a
    command: "{python} check.py"
    results:
      cucumber_json: target/cucumber-report.json
    agent:
      agent_command: "{python} fake_agent.py"    # sonra kaldırıp: agent_cli: opencode
      scenario_command: "{python} check.py"
      edit_whitelist:
        - pages/

  - id: heal-b
    name: "Heal Testi B (assertion hatasi)"
    path: $DestYaml/heal-fixture-b
    command: "{python} check.py"
    results:
      cucumber_json: target/cucumber-report.json
    agent:
      agent_command: "{python} fake_agent.py"    # sonra kaldırıp: agent_cli: opencode
      scenario_command: "{python} check.py"
      edit_whitelist:
        - steps/
"@
