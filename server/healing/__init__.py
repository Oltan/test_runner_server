"""Faz 2: LLM destekli test düzeltme (healing).

Mod A — locator kırılmaları: agent yok; deterministik topla → tek LLM
çağrısı → deterministik patch → yeniden koş.
Mod B — assertion/akış hataları: coding agent (opencode) dar görevle
worktree içinde çalışır; sonrasında diff whitelist ile sert kontrol.

Her heal denemesi izole bir git worktree'de, kendi branch'inde yapılır ve
insan onayı olmadan hiçbir şey ana koda karışmaz.
"""


class HealError(Exception):
    """Pipeline'ı durduran, kullanıcıya gösterilecek hata."""
