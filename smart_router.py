"""Compat layer vazio para evitar importações quebradas do legado."""

from __future__ import annotations

from typing import AsyncIterator


class SmartRouter:
    """Stub legado: direcione consumidores para ``pipeline.process_user_input``."""

    async def route_and_respond(self, *_args, **_kwargs) -> AsyncIterator[str]:
        yield (
            "A arquitetura da Ceci foi atualizada para o modelo LLM-first."
            " Utilize `pipeline.process_user_input` diretamente."
        )