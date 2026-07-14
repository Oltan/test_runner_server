from pathlib import Path

from server.parsers import collect_stats, parse_cucumber_json, parse_junit_xml_dir

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_cucumber_json():
    stats = parse_cucumber_json(FIXTURES / "cucumber-report.json")
    assert stats.passed == 2
    assert stats.failed == 1
    assert stats.skipped == 1
    assert stats.total == 4

    failed = [s for s in stats.scenarios if s.status == "failed"]
    assert len(failed) == 1
    assert failed[0].scenario == "Kilitli kullanıcı"
    assert "NoSuchElementException" in failed[0].error_message
    # background elementi senaryo olarak sayılmamalı
    names = {s.scenario for s in stats.scenarios}
    assert "ortak adımlar" not in names


def test_parse_junit_xml_dir():
    stats = parse_junit_xml_dir(FIXTURES / "surefire")
    assert stats.passed == 2
    assert stats.failed == 1
    assert stats.skipped == 1
    assert stats.total == 4
    failed = [s for s in stats.scenarios if s.status == "failed"]
    assert failed[0].scenario == "Kilitli kullanıcı"
    assert "Unable to locate element" in failed[0].error_message


def test_collect_stats_prefers_cucumber_json():
    stats = collect_stats(FIXTURES, "cucumber-report.json", "surefire")
    assert stats is not None
    # cucumber json'daki senaryo detayları (error_message) gelmiş olmalı
    assert any("NoSuchElementException" in (s.error_message or "")
               for s in stats.scenarios)


def test_collect_stats_falls_back_to_junit():
    stats = collect_stats(FIXTURES, "yok-boyle-dosya.json", "surefire")
    assert stats is not None
    assert stats.total == 4


def test_collect_stats_none_when_no_reports(tmp_path):
    assert collect_stats(tmp_path, "yok.json", "yok-dizin") is None


def test_collect_stats_rejects_stale_reports(tmp_path):
    """Durdurulan koşuma önceki koşumun bayat raporu mal edilmemeli."""
    import shutil
    import time

    shutil.copy(FIXTURES / "cucumber-report.json", tmp_path / "report.json")
    (tmp_path / "surefire").mkdir()
    shutil.copy(FIXTURES / "surefire" / "TEST-runner.CucumberTest.xml",
                tmp_path / "surefire")

    future = time.time() + 60  # koşum, rapor dosyalarından SONRA başlamış gibi
    assert collect_stats(tmp_path, "report.json", "surefire",
                         since=future) is None
    # eşik geçmişteyse raporlar kabul edilir
    past = time.time() - 60
    stats = collect_stats(tmp_path, "report.json", "surefire", since=past)
    assert stats is not None and stats.total == 4
