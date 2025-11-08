"""Quick integration smoke tests for Ceci's LLM-first pipeline."""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, List, Optional

import jwt

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline import process_user_input


SECRET = "minhaChaveSuperSecretaParaJwtComTamanhoAdequado!"
TRANSIENT_ERRORS = (
    "enfrentei um problema",
    "tente novamente",
    "problema temporário",
    "não foi possível"  # casos gerais de falha de modelo
)


@dataclass
class TestCase:
    name: str
    prompt: str
    user_type: str = "Passageiro"
    token: Optional[str] = None
    expectations: Iterable[str] = field(default_factory=list)
    forbidden: Iterable[str] = field(default_factory=list)


async def collect_response(message: str, user_type: str, token: Optional[str]) -> str:
    chunks: List[str] = []
    async for chunk in process_user_input(message, user_type, token):
        chunks.append(chunk)
    return "".join(chunks).strip()


def build_collaborator_token(login: str = "teste.colaborador") -> str:
    payload = {
        "login": login,
        "sub": login,
        "name": "Colaborador de Teste",
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    return jwt.encode(payload, SECRET, algorithm="HS256")


async def run_cases() -> None:
    collaborator_token = f"Bearer {build_collaborator_token()}"

    cases = [
        TestCase(
            name="FAQ passageiro",
            prompt="Como posso recarregar o Bilhete Único do metrô?",
            expectations=["bilhete", "recar"],
        ),
        TestCase(
            name="Tarifa atual",
            prompt="Qual é a tarifa atual do metrô de São Paulo?",
            expectations=["5,20", "tarifa"],
        ),
        TestCase(
            name="Rota simples",
            prompt="Preciso ir no metrô da estação Sé até a estação Paulista, qual o melhor caminho?",
            expectations=["Sé", "Paulista"],
        ),
        TestCase(
            name="Emergência",
            prompt="Socorro, acabei de sofrer um assédio no metrô!",
            expectations=["segurança", "contato"],
        ),
        TestCase(
            name="Fallback informativo",
            prompt="Quais atrações turísticas existem perto da estação Luz do metrô?",
            expectations=["Luz"],
        ),
        TestCase(
            name="Pergunta ampla permitida",
            prompt="Quais ônibus passam na estação Jabaquara?",
            expectations=["Jabaquara"],
            forbidden=["transporte público de são paulo"],
        ),
        TestCase(
            name="Estação sem palavra metrô",
            prompt="Como chego em Vila Madalena saindo da Sé?",
            expectations=["Vila Madalena"],
            forbidden=["transporte público de são paulo"],
        ),
        TestCase(
            name="FAQ em inglês",
            prompt="How can I recharge my Bilhete Único card for the metro?",
            expectations=["bilhete", "recharge"],
        ),
        TestCase(
            name="Rota em espanhol",
            prompt="Necesito ir en el metro desde la estación Sé hasta Paulista, ¿cuál es la mejor ruta?",
            expectations=["Sé", "Paulista"],
        ),
        TestCase(
            name="Smalltalk em italiano",
            prompt="Ciao Ceci! Come posso aiutarti oggi nel metrò di San Paolo?",
            expectations=["ciao", "trasporto"],
        ),
        TestCase(
            name="Pergunta em francês",
            prompt="Quelles lignes du métro passent par la station Luz?",
            expectations=["Luz", "ligne"],
        ),
        TestCase(
            name="Relatório colaborador",
            prompt="Gerar relatório sobre falha elétrica na Linha 9 hoje às 7h",
            user_type="Colaborador",
            token=collaborator_token,
            expectations=["Relatório", "PDF"],
        ),
        TestCase(
            name="Relatório colaborador token com aspas",
            prompt="Gerar relatório sobre falha elétrica no metrô Linha 4 hoje às 8h",
            user_type="Colaborador",
            token=f'"Bearer {build_collaborator_token("teste.token")}"',
            expectations=["Relatório", "PDF"],
        ),
        TestCase(
            name="Guardrail assunto geral",
            prompt="Quem inventou a lâmpada?",
            expectations=["transporte público de São Paulo"],
        ),
        TestCase(
            name="Guardrail pedido de código",
            prompt="Escreva um script em Python para ordenar uma lista.",
            expectations=["transporte público de São Paulo"],
        ),
    ]

    failures = 0

    for case in cases:
        print(f"\n=== {case.name} ===")
        print(f"Usuário: {case.user_type}\nPergunta: {case.prompt}")
        max_attempts = 2
        for attempt in range(1, max_attempts + 1):
            response = await collect_response(case.prompt, case.user_type, case.token)
            normalized_attempt = response.lower()
            if any(err in normalized_attempt for err in TRANSIENT_ERRORS) and attempt < max_attempts:
                print("⚠️  Resposta sinalizou erro transitório, tentando novamente...")
                await asyncio.sleep(1)
                continue
            break
        print("Resposta:\n" + response)

        normalized = response.lower()
        unmet = [snippet for snippet in case.expectations if snippet.lower() not in normalized]
        forbidden_hits = [snippet for snippet in case.forbidden if snippet.lower() in normalized]
        if unmet:
            failures += 1
            print(f"⚠️  Expectativas não encontradas: {', '.join(unmet)}")

        if forbidden_hits:
            failures += 1
            print(f"⚠️  Conteúdo inesperado presente: {', '.join(forbidden_hits)}")

        if not unmet and not forbidden_hits:
            print("✅  Expectativas atendidas")
    if failures:
        raise SystemExit(f"{failures} caso(s) falhou/falharam – verifique o log acima.")
    print("\nTodos os casos passaram.")


if __name__ == "__main__":
    asyncio.run(run_cases())