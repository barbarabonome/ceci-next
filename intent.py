"""Compat layer para projetos antigos; usa heurística mínima."""

from __future__ import annotations


def detect_intent(user_input: str) -> str:
    """Retorna sempre ``"fallback"``. Mantenha para compatibilidade legado."""
    return "fallback"