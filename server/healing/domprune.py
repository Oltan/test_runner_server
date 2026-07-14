"""DOM budama: hata anındaki sayfadan, kırılan locator'a benzeyen aday
elementleri seçip küçük bir metin bloğuna indirger.

Amaç: 30-100k token'lık ham DOM yerine LLM'e 1-2k token'lık hedefli kesit
vermek — küçük prompt hem daha isabetli cevap hem daha hızlı inference.
Sadece stdlib (html.parser) kullanır.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser

_SKIP_CONTENT = {"script", "style", "svg", "noscript", "template"}
_INTERACTIVE = {"button", "input", "a", "select", "textarea", "label", "form"}
_ATTR_KEEP = ("id", "name", "class", "type", "href", "value", "placeholder",
              "title", "role", "aria-label", "data-testid", "data-test",
              "data-qa", "fx_id", "styleclass")


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-zA-Z0-9_-]{3,}", text.lower())}


@dataclass
class _Element:
    tag: str
    attrs: dict[str, str]
    path: str
    text: str = ""
    depth: int = 0

    def render(self) -> str:
        attrs = " ".join(f'{k}="{v[:80]}"' for k, v in self.attrs.items()
                         if k in _ATTR_KEEP and v)
        text = re.sub(r"\s+", " ", self.text).strip()[:80]
        inner = f">{text}</{self.tag}>" if text else "/>"
        return f"<{self.tag}{' ' + attrs if attrs else ''}{inner}   (yol: {self.path})"


class _Collector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.elements: list[_Element] = []
        self._stack: list[_Element] = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if self._skip_depth or tag in _SKIP_CONTENT:
            if tag in _SKIP_CONTENT or self._skip_depth:
                self._skip_depth += 1
            return
        parent = self._stack[-1] if self._stack else None
        crumb = tag
        attr_dict = {k: (v or "") for k, v in attrs}
        if attr_dict.get("id"):
            crumb += f"#{attr_dict['id']}"
        path = (parent.path + ">" if parent else "") + crumb
        el = _Element(tag=tag, attrs=attr_dict, path=path,
                      depth=len(self._stack))
        self.elements.append(el)
        self._stack.append(el)

    def handle_endtag(self, tag):
        if self._skip_depth:
            self._skip_depth -= 1
            return
        for i in range(len(self._stack) - 1, -1, -1):
            if self._stack[i].tag == tag:
                del self._stack[i:]
                break

    def handle_data(self, data):
        if self._skip_depth or not self._stack:
            return
        if data.strip():
            self._stack[-1].text += data


def prune_dom(html: str, locator_value: str, top: int = 12,
              max_chars: int = 6000) -> str:
    """Locator'a benzerlik skoruna göre en iyi aday elementleri döndürür."""
    collector = _Collector()
    try:
        collector.feed(html)
    except Exception:  # bozuk HTML'de eldekiyle devam
        pass

    loc_tokens = _tokens(locator_value)
    scored: list[tuple[float, _Element]] = []
    for el in collector.elements:
        hay = " ".join([el.attrs.get(k, "") for k in _ATTR_KEEP]) + " " + el.text[:120]
        overlap = len(_tokens(hay) & loc_tokens)
        score = overlap * 2.0
        if el.tag in loc_tokens:
            score += 2.0
        if el.tag in _INTERACTIVE:
            score += 1.0
        if score > 0:
            scored.append((score, el))

    scored.sort(key=lambda pair: -pair[0])
    chosen = [el for _, el in scored[:top]]
    if not chosen:  # hiç benzerlik yoksa etkileşimli elementleri ver
        chosen = [el for el in collector.elements
                  if el.tag in _INTERACTIVE][:top]

    out: list[str] = []
    used = 0
    for el in chosen:
        line = "- " + el.render()
        if used + len(line) > max_chars:
            break
        out.append(line)
        used += len(line)
    return "\n".join(out)
