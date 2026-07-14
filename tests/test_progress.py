import json

from server.progress import ProgressTracker


def _line(obj) -> str:
    return json.dumps(obj)


def test_tracker_counts_scenarios():
    t = ProgressTracker()
    # koşum başında tüm pickle'lar yazılır → toplam
    for i in range(3):
        assert t.feed_line(_line({"pickle": {"id": f"p{i}", "name": f"s{i}"}}))
    assert t.total == 3

    # 1. senaryo: geçer
    t.feed_line(_line({"testCaseStarted": {"id": "c1"}}))
    t.feed_line(_line({"testStepFinished": {
        "testCaseStartedId": "c1", "testStepResult": {"status": "PASSED"}}}))
    assert t.feed_line(_line({"testCaseFinished": {"testCaseStartedId": "c1"}}))
    assert (t.passed, t.failed, t.done) == (1, 0, 1)

    # 2. senaryo: bir adımı FAIL, sonrakiler SKIPPED → failed
    t.feed_line(_line({"testCaseStarted": {"id": "c2"}}))
    t.feed_line(_line({"testStepFinished": {
        "testCaseStartedId": "c2", "testStepResult": {"status": "FAILED"}}}))
    t.feed_line(_line({"testStepFinished": {
        "testCaseStartedId": "c2", "testStepResult": {"status": "SKIPPED"}}}))
    t.feed_line(_line({"testCaseFinished": {"testCaseStartedId": "c2"}}))
    assert (t.passed, t.failed, t.done) == (1, 1, 2)

    snap = t.snapshot()
    assert snap["total"] == 3
    assert snap["percent"] == 66.7


def test_tracker_ignores_retried_case():
    t = ProgressTracker()
    t.feed_line(_line({"pickle": {"id": "p0"}}))
    t.feed_line(_line({"testCaseStarted": {"id": "c1"}}))
    t.feed_line(_line({"testStepFinished": {
        "testCaseStartedId": "c1", "testStepResult": {"status": "FAILED"}}}))
    # cucumber retry edecekse sayılmamalı
    t.feed_line(_line({"testCaseFinished": {"testCaseStartedId": "c1",
                                            "willBeRetried": True}}))
    assert t.done == 0


def test_tracker_survives_garbage():
    t = ProgressTracker()
    assert not t.feed_line("bozuk satır {{{")
    assert not t.feed_line("")
    assert not t.feed_line(_line({"alakasizMesaj": {}}))
    assert t.done == 0
