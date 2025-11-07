"""Compat layer legado sem dependências pesadas."""

from __future__ import annotations


def build_prompt(_contexto: dict, _user_input: str, _mode: str = "chat") -> str:
    """Módulo não é mais utilizado na arquitetura atual."""
    raise RuntimeError(
        "prompt_builder foi descontinuado. Utilize o orchestrator LLM-first para gerar respostas."
    )