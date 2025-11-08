from __future__ import annotations

from typing import Optional
from functools import lru_cache

from orchestrator import LLMOrchestrator


@lru_cache(maxsize=1)
def get_orchestrator() -> LLMOrchestrator:
    """
    Cria o orquestrador só na primeira vez que for usado.
    Isso evita crash no deploy quando a OPENAI_API_KEY ainda não foi lida.
    """
    return LLMOrchestrator()


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
    """
    Gera chunks da resposta do LLM, mantendo a mesma assinatura que você já usa.
    """
    orchestrator = get_orchestrator()
    session_key = _build_session_id(tipo_usuario, token, session_id)

    # mantém o streaming
    async for chunk in orchestrator.handle_message(
        session_key,
        user_input,
        tipo_usuario,
        token,
    ):
        yield chunk
