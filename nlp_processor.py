"""Stub legado para compatibilidade; pipeline atual não usa este módulo."""

from __future__ import annotations


def nlp_pipeline(_user_input: str) -> dict:
    return {"error": "O pipeline NLP local foi desativado na arquitetura LLM-first."}
