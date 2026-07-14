import subprocess
from pathlib import Path

import pytest

from server.healing import HealError
from server.healing.classify import classify
from server.healing.domprune import prune_dom
from server.healing.llm import extract_json_block
from server.healing.locator import extract_locator, find_occurrences
from server.healing.patch import apply_single_literal_patch, whitelist_violations

SELENIUM_JSON_ERROR = (
    "org.openqa.selenium.NoSuchElementException: Unable to locate element: "
    '{"method":"xpath","selector":"//button[@id=\'submit-btn\']"}\n'
    "  at ...")

SELENIUM_BY_ERROR = (
    "org.openqa.selenium.TimeoutException: Expected condition failed: "
    "waiting for visibility of element located by By.cssSelector: "
    ".login-form .submit (tried for 10 second(s))")


# --- classify -----------------------------------------------------------------

def test_classify_locator():
    assert classify(SELENIUM_JSON_ERROR) == "locator"
    assert classify(SELENIUM_BY_ERROR) == "locator"
    assert classify("NodeQueryException: no nodes matched #loginBtn") == "locator"


def test_classify_logic_infra_unknown():
    assert classify("java.lang.AssertionError: expected:<5> but was:<3>") == "logic"
    assert classify("SessionNotCreatedException: chrome not reachable") == "infra"
    assert classify("java.lang.NullPointerException at Foo.java:10") == "unknown"
    assert classify(None) == "unknown"


# --- locator çıkarımı ------------------------------------------------------------

def test_extract_locator_selenium_json():
    assert extract_locator(SELENIUM_JSON_ERROR) == (
        "xpath", "//button[@id='submit-btn']")


def test_extract_locator_by_format():
    assert extract_locator(SELENIUM_BY_ERROR) == (
        "css", ".login-form .submit")


def test_extract_locator_none():
    assert extract_locator("java.lang.AssertionError: beklenen 5") is None


# --- kod arama + patch ------------------------------------------------------------

@pytest.fixture
def fake_repo(tmp_path):
    pages = tmp_path / "pages"
    pages.mkdir()
    (pages / "LoginPage.java").write_text(
        'public class LoginPage {\n'
        '    By submit = By.xpath("//button[@id=\'submit-btn\']");\n'
        '}\n', encoding="utf-8")
    (tmp_path / "pom.xml").write_text("<project/>", encoding="utf-8")
    return tmp_path


def test_find_occurrences(fake_repo):
    hits = find_occurrences(fake_repo, ["pages/"], "//button[@id='submit-btn']")
    assert len(hits) == 1
    assert hits[0][1] == 1


def test_patch_single_match(fake_repo):
    path = apply_single_literal_patch(
        fake_repo, ["pages/"],
        "//button[@id='submit-btn']", "//button[@id='submit-button-v2']")
    text = path.read_text(encoding="utf-8")
    assert "submit-button-v2" in text and "submit-btn'" not in text


def test_patch_rejects_multiple_matches(fake_repo):
    (fake_repo / "pages" / "OtherPage.java").write_text(
        'By b = By.xpath("//button[@id=\'submit-btn\']");',
        encoding="utf-8")
    with pytest.raises(HealError, match="insan onayı"):
        apply_single_literal_patch(fake_repo, ["pages/"],
                                   "//button[@id='submit-btn']", "yeni")


def test_patch_rejects_not_found(fake_repo):
    with pytest.raises(HealError, match="bulunamadı"):
        apply_single_literal_patch(fake_repo, ["pages/"], "yok-boyle", "yeni")


# --- DOM budama --------------------------------------------------------------------

def test_prune_dom_finds_candidates():
    html = """<html><head><script>ignore()</script></head><body>
      <div class="menu"><a href="/x">Link</a></div>
      <form id="order-form">
        <button id="submit-button-v2" class="btn">Gönder</button>
        <button id="cancel-btn" class="btn">Vazgeç</button>
      </form></body></html>"""
    result = prune_dom(html, "//button[@id='submit-btn']")
    assert "submit-button-v2" in result   # benzer id'li aday listede
    assert "ignore()" not in result       # script içeriği atıldı


def test_prune_dom_empty_similarity_falls_back():
    html = "<body><button id='a'>X</button><p>metin</p></body>"
    result = prune_dom(html, "//tr[@data-row='42']")
    assert "button" in result  # benzerlik yok → etkileşimli elementler


# --- whitelist ---------------------------------------------------------------------

@pytest.fixture
def git_worktree(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-q", "--allow-empty", "-m", "init"],
                   cwd=tmp_path, check=True)
    (tmp_path / "src/test/java/pages").mkdir(parents=True)
    return tmp_path


def test_whitelist_clean(git_worktree):
    (git_worktree / "src/test/java/pages/A.java").write_text("x")
    assert whitelist_violations(git_worktree, ["src/test/java/"]) == []


def test_whitelist_violation(git_worktree):
    (git_worktree / "src/test/java/pages/A.java").write_text("x")
    (git_worktree / "pom.xml").write_text("<project/>")
    violations = whitelist_violations(git_worktree, ["src/test/java/"])
    assert violations == ["pom.xml"]


# --- LLM cevap ayrıştırma -------------------------------------------------------------

def test_extract_json_block_with_fences():
    text = ('Tabii, işte cevap:\n```json\n{"selector_type": "xpath", '
            '"selector": "//button[@id=\'x\']", "reason": "id değişti"}\n```')
    parsed = extract_json_block(text)
    assert parsed["selector"] == "//button[@id='x']"


def test_extract_json_block_invalid():
    with pytest.raises(HealError):
        extract_json_block("hiç json yok burada")
