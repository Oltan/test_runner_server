"""Faz 2: LLM destekli test düzeltme (healing).

Her başarısız senaryo (locator kırılması dahil) aynı coding agent'a
(opencode/Claude Code) gider — agent repoya tam erişimle dosyayı bulur,
hatayı anlar, düzeltmeyi kendisi yapar. Sunucu kendi regex/JSON/literal-
patch mekanizmasıyla uğraşmaz (dar kapsamlı olurdu). Hata sınıflandırması
sadece agent'a hangi görev şablonunun verileceğini seçer; ardından diff
whitelist ile sert kontrol uygulanır.

Her heal denemesi izole bir git worktree'de, kendi branch'inde yapılır ve
insan onayı olmadan hiçbir şey ana koda karışmaz.
"""


class HealError(Exception):
    """Pipeline'ı durduran, kullanıcıya gösterilecek hata."""
