from __future__ import annotations

from typing import Optional

from orchestrator import LLMOrchestrator


_orchestrator = LLMOrchestrator()


def _build_session_id(
    tipo_usuario: str,
    token: Optional[str],
    session_override: Optional[str],
) -> str:
    if session_override:
        return session_override

    if tipo_usuario == "Colaborador" and token:
        return f"collaborator::{token}"

    return f"{tipo_usuario.lower()}::anon"


async def process_user_input(
    user_input: str,
    tipo_usuario: str = "Passageiro",
    token: Optional[str] = None,
    *,
    session_id: Optional[str] = None,
):
    session_key = _build_session_id(tipo_usuario, token, session_id)
    async for chunk in _orchestrator.handle_message(session_key, user_input, tipo_usuario, token):
        yield chunk
