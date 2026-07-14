#!/usr/bin/env python3
"""Cucumber-JVM koşumunu taklit eden sahte proje.

Gerçek bir Cucumber koşumunun ürettiği çıktıları üretir:
  - target/cucumber-messages.ndjson  (koşum SIRASINDA satır satır — canlı ilerleme)
  - target/cucumber-report.json      (koşum SONUNDA — kesin istatistik)
  - target/rerun.txt                 (FAIL eden senaryolar — retry girdisi)
  - target/failure-artifacts/<senaryo>/  (deterministik FAIL'lerde DOM dump +
                                          meta — healing girdisi)

Kullanım:
  python3 run.py            normal koşum (tüm senaryolar)
  python3 run.py --rerun    sadece target/rerun.txt içindeki senaryolar
                            (flaky senaryolar bu modda GEÇER — retry simülasyonu)

Ortam değişkenleri:
  FAKE_FAILING     deterministik FAIL sayısı (varsayılan 1)
  FAKE_FLAKY       flaky senaryo sayısı: ilk koşumda FAIL, rerun'da PASS (varsayılan 0)
  FAKE_STEP_DELAY  adım başına bekleme saniyesi (varsayılan 0.4)
"""
import json
import os
import re
import sys
import time
from pathlib import Path

FAILING = int(os.environ.get("FAKE_FAILING", "1"))
FLAKY = int(os.environ.get("FAKE_FLAKY", "0"))
STEP_DELAY = float(os.environ.get("FAKE_STEP_DELAY", "0.4"))
RERUN_MODE = "--rerun" in sys.argv

# (feature, senaryo, adımlar)
SCENARIOS = [
    ("Giriş", "Başarılı giriş",
     ["kullanıcı giriş sayfasında", "geçerli bilgilerle giriş yapar", "ana sayfa görünür"]),
    ("Giriş", "Hatalı şifre uyarısı",
     ["kullanıcı giriş sayfasında", "yanlış şifreyle giriş yapar", "hata mesajı görünür"]),
    ("Giriş", "Kilitli kullanıcı",
     ["kullanıcı giriş sayfasında", "kilitli hesapla giriş yapar", "kilit uyarısı görünür"]),
    ("Sepet", "Ürün sepete eklenir",
     ["kullanıcı giriş yapmış", "ürün detayına gider", "sepete ekler", "sepette ürün görünür"]),
    ("Sepet", "Sepetten ürün silinir",
     ["sepette ürün var", "ürünü siler", "sepet boş görünür"]),
    ("Sepet", "Kupon uygulanır",
     ["sepette ürün var", "kupon kodu girer", "indirim uygulanır"]),
    ("Rapor", "Sipariş raporu indirilir",
     ["kullanıcı rapor sayfasında", "tarih aralığı seçer", "raporu indirir"]),
    ("Rapor", "Boş rapor uyarısı",
     ["kullanıcı rapor sayfasında", "veri olmayan aralık seçer", "uyarı görünür"]),
]

TARGET = Path(__file__).parent / "target"

ERROR_MESSAGE = (
    "org.openqa.selenium.NoSuchElementException: "
    "Unable to locate element: "
    "{\"method\":\"xpath\",\"selector\":\"//button[@id='submit-btn']\"}")

# Healing testleri için: hata anındaki DOM'da locator'ın YENİ hali var
FAILURE_DOM = """<!DOCTYPE html>
<html><head><title>Sipariş Sayfası</title><script>var x=1;</script></head>
<body>
  <div id="app"><nav class="topbar"><a href="/home">Ana sayfa</a></nav>
    <main><form id="order-form" class="form">
      <input id="date-range" name="dateRange" placeholder="Tarih aralığı"/>
      <button id="submit-button-v2" class="btn btn-primary" type="submit">Gönder</button>
      <button id="cancel-btn" class="btn" type="button">Vazgeç</button>
    </form></main></div>
</body></html>"""


def _sanitize(name: str) -> str:
    return re.sub(r"[^\w-]+", "_", name, flags=re.UNICODE)


def main() -> int:
    TARGET.mkdir(exist_ok=True)

    # deterministik FAIL: sondan FAILING senaryo; flaky: onların hemen öncesi
    names = [s[1] for s in SCENARIOS]
    failing = set(names[len(names) - FAILING:]) if FAILING else set()
    flaky = set(names[len(names) - FAILING - FLAKY:len(names) - FAILING]) \
        if FLAKY else set()

    if RERUN_MODE:
        rerun_file = TARGET / "rerun.txt"
        wanted = {line.strip() for line in
                  rerun_file.read_text(encoding="utf-8").splitlines()
                  if line.strip()} if rerun_file.is_file() else set()
        scenarios = [s for s in SCENARIOS if s[1] in wanted]
        # retry'da flaky'ler geçer, deterministik olanlar yine kalır
        fails_now = failing & wanted
    else:
        scenarios = SCENARIOS
        fails_now = failing | flaky

    ndjson = open(TARGET / "cucumber-messages.ndjson", "w", encoding="utf-8")

    def emit(msg: dict) -> None:
        ndjson.write(json.dumps(msg, ensure_ascii=False) + "\n")
        ndjson.flush()

    emit({"meta": {"implementation": {"name": "fake-cucumber-sim"}}})
    for i, (_, name, _steps) in enumerate(scenarios):
        emit({"pickle": {"id": f"pickle-{i}", "name": name}})
    emit({"testRunStarted": {"timestamp": {"seconds": int(time.time())}}})
    mode = "RETRY koşumu" if RERUN_MODE else "normal koşum"
    print(f"{len(scenarios)} senaryo koşulacak ({mode}, "
          f"{len(fails_now & {s[1] for s in scenarios})} FAIL bekleniyor)\n",
          flush=True)

    report: dict[str, list] = {}
    failed_names: list[str] = []

    for i, (feature, name, steps) in enumerate(scenarios):
        case_id = f"tcs-{i}"
        will_fail = name in fails_now
        emit({"testCaseStarted": {"id": case_id, "testCaseId": f"tc-{i}"}})
        print(f"Senaryo: {name}    # features/{feature.lower()}.feature",
              flush=True)

        element_steps = []
        scenario_failed = False
        for j, step_name in enumerate(steps):
            time.sleep(STEP_DELAY)
            if scenario_failed:
                status, mark, error = "SKIPPED", "-", None
            elif will_fail and j == 1:
                status, mark, error = "FAILED", "✗", ERROR_MESSAGE
                scenario_failed = True
            else:
                status, mark, error = "PASSED", "✓", None
            emit({"testStepFinished": {
                "testCaseStartedId": case_id,
                "testStepId": f"ts-{i}-{j}",
                "testStepResult": {"status": status,
                                   "duration": {"nanos": int(STEP_DELAY * 1e9)}},
            }})
            print(f"  {mark} {step_name}", flush=True)
            if error:
                print(f"      {error}", flush=True)
            result = {"status": status.lower(),
                      "duration": int(STEP_DELAY * 1e9)}
            if error:
                result["error_message"] = error
            element_steps.append({"keyword": "Given " if j == 0 else "When ",
                                  "name": step_name, "result": result})

        emit({"testCaseFinished": {"testCaseStartedId": case_id,
                                   "willBeRetried": False}})
        print("", flush=True)
        if scenario_failed:
            failed_names.append(name)
            # deterministik hata için artefakt (healing girdisi)
            if name in failing:
                art_dir = TARGET / "failure-artifacts" / _sanitize(name)
                art_dir.mkdir(parents=True, exist_ok=True)
                (art_dir / "tab_0.html").write_text(FAILURE_DOM,
                                                    encoding="utf-8")
                (art_dir / "meta.json").write_text(json.dumps({
                    "scenario": name, "tabs": [{"active": "true",
                    "url": "http://uygulama/rapor", "dom_file": "tab_0.html"}],
                }, ensure_ascii=False), encoding="utf-8")
        report.setdefault(feature, []).append({
            "type": "scenario", "keyword": "Scenario",
            "name": name, "steps": element_steps,
        })

    emit({"testRunFinished": {"success": not failed_names}})
    ndjson.close()

    (TARGET / "rerun.txt").write_text("\n".join(failed_names),
                                      encoding="utf-8")
    cucumber_json = [
        {"uri": f"features/{feature.lower()}.feature", "name": feature,
         "elements": elements}
        for feature, elements in report.items()
    ]
    with open(TARGET / "cucumber-report.json", "w", encoding="utf-8") as f:
        json.dump(cucumber_json, f, ensure_ascii=False, indent=2)

    print("Koşum bitti:", "FAILED" if failed_names else "PASSED", flush=True)
    return 1 if failed_names else 0


if __name__ == "__main__":
    sys.exit(main())
