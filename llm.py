"""Helper para inicializar o cliente AsyncOpenAI uma única vez."""

from __future__ import annotations

import os
from functools import lru_cache

import dotenv
from openai import AsyncOpenAI


dotenv.load_dotenv()


@lru_cache(maxsize=1)
def get_async_client() -> AsyncOpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY não configurada no ambiente.")
    return AsyncOpenAI(api_key=api_key)

            