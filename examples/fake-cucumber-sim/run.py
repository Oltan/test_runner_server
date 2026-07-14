#!/usr/bin/env python3
"""Cucumber-JVM koşumunu taklit eden sahte proje.

Gerçek bir Cucumber koşumunun ürettiği iki çıktıyı üretir:
  - target/cucumber-messages.ndjson  (koşum SIRASINDA satır satır — canlı ilerleme)
  - target/cucumber-report.json      (koşum SONUNDA — kesin istatistik)

Ortam değişkenleri:
  FAKE_FAILING     kaç senaryo FAIL etsin (varsayılan 1)
  FAKE_STEP_DELAY  adım başına bekleme saniyesi (varsayılan 0.4)
"""
import json
import os
import sys
import time
from pathlib import Path

FAILING = int(os.environ.get("FAKE_FAILING", "1"))
STEP_DELAY = float(os.environ.get("FAKE_STEP_DELAY", "0.4"))

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


def main() -> int:
    TARGET.mkdir(exist_ok=True)
    ndjson = open(TARGET / "cucumber-messages.ndjson", "w", encoding="utf-8")

    def emit(msg: dict) -> None:
        ndjson.write(json.dumps(msg, ensure_ascii=False) + "\n")
        ndjson.flush()

    # Sondan başlayarak FAILING kadar senaryo FAIL eder (2. adımında)
    failing_idx = {len(SCENARIOS) - 1 - i for i in range(min(FAILING, len(SCENARIOS)))}

    emit({"meta": {"implementation": {"name": "fake-cucumber-sim"}}})
    for i, (feature, name, _) in enumerate(SCENARIOS):
        emit({"pickle": {"id": f"pickle-{i}", "name": name,
                         "uri": f"features/{feature.lower()}.feature"}})
    emit({"testRunStarted": {"timestamp": {"seconds": int(time.time())}}})
    print(f"{len(SCENARIOS)} senaryo koşulacak "
          f"({len(failing_idx)} tanesi FAIL edecek)\n", flush=True)

    report = {}  # feature -> elements listesi
    any_failed = False

    for i, (feature, name, steps) in enumerate(SCENARIOS):
        case_started_id = f"tcs-{i}"
        will_fail = i in failing_idx
        emit({"testCaseStarted": {"id": case_started_id, "testCaseId": f"tc-{i}"}})
        print(f"Senaryo: {name}    # features/{feature.lower()}.feature", flush=True)

        elements_steps = []
        scenario_failed = False
        for j, step in enumerate(steps):
            time.sleep(STEP_DELAY)
            if scenario_failed:
                status, mark, err = "SKIPPED", "-", None
            elif will_fail and j == 1:
                status, mark = "FAILED", "✗"
                err = ("org.openqa.selenium.NoSuchElementException: "
                       "Unable to locate element: "
                       "{\"method\":\"xpath\",\"selector\":\"//button[@id='submit-btn']\"}")
                scenario_failed = True
                any_failed = True
            else:
                status, mark, err = "PASSED", "✓", None
            emit({"testStepFinished": {
                "testCaseStartedId": case_started_id,
                "testStepId": f"ts-{i}-{j}",
                "testStepResult": {"status": status,
                                   "duration": {"nanos": int(STEP_DELAY * 1e9)}},
            }})
            print(f"  {mark} {step}", flush=True)
            if err:
                print(f"      {err}", flush=True)
            result = {"status": status.lower(),
                      "duration": int(STEP_DELAY * 1e9)}
            if err:
                result["error_message"] = err
            elements_steps.append({"keyword": "Given " if j == 0 else "When ",
                                   "name": step, "result": result})

        emit({"testCaseFinished": {"testCaseStartedId": case_started_id,
                                   "willBeRetried": False}})
        print("", flush=True)
        report.setdefault(feature, []).append({
            "type": "scenario", "keyword": "Scenario",
            "name": name, "steps": elements_steps,
        })

    emit({"testRunFinished": {"success": not any_failed}})
    ndjson.close()

    cucumber_json = [
        {"uri": f"features/{feature.lower()}.feature", "name": feature,
         "elements": elements}
        for feature, elements in report.items()
    ]
    with open(TARGET / "cucumber-report.json", "w", encoding="utf-8") as f:
        json.dump(cucumber_json, f, ensure_ascii=False, indent=2)

    print("Koşum bitti:", "FAILED" if any_failed else "PASSED", flush=True)
    return 1 if any_failed else 0


if __name__ == "__main__":
    sys.exit(main())
