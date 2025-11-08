"""Módulo responsável por orquestrar respostas via OpenAI com MCP LLM-first."""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional, cast

from llm import get_async_client
from rag_index import KnowledgeIndex
from services import relatorio_service, rota_service
from unidecode import unidecode
from openai.types.chat import ChatCompletionMessageParam, ChatCompletionToolParam


EMERGENCY_PATTERNS = re.compile(
    r"\b(ass[eé]dio|roubado|roubaram|roubo|viol[eê]ncia|agress[aã]o|perigo|ajuda|socorro|emerg[eê]ncia|harassment|robbed|stolen|robbery|violence|aggression|danger|help|emergency|acoso|robaron|robo|violencia|agresi[oó]n|peligro|ayuda|emergencia)\b",
    re.IGNORECASE,
)


@dataclass
class SessionState:
    messages: List[Dict[str, Any]] = field(default_factory=list)

    def append(self, message: Dict[str, Any]) -> None:
        self.messages.append(message)

    def prune(self, max_messages: int = 20) -> None:
        if len(self.messages) <= max_messages:
            return
        # Mantém o histórico mais recente para evitar custo excessivo
        self.messages = self.messages[-max_messages:]


class ToolRegistry:
    """Registra e executa ferramentas disponíveis para o modelo."""

    def __init__(self, knowledge_index: KnowledgeIndex) -> None:
        self._knowledge_index = knowledge_index

    def list_tools(self, tipo_usuario: str) -> List[Dict[str, Any]]:
        tools: List[Dict[str, Any]] = [
            {
                "type": "function",
                "function": {
                    "name": "search_knowledge",
                    "description": (
                        "Busca informações na base de conhecimento da Ceci. Utilize sempre que precisar de dados,"
                        " políticas ou respostas frequentes para passageiros ou colaboradores."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Pergunta ou assunto a ser pesquisado na base.",
                            },
                            "top_k": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 5,
                                "default": 3,
                            },
                        },
                        "required": ["query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "plan_route",
                    "description": (
                        "Calcula a melhor rota entre estações da CPTM/Metrô. Exija sempre origem e destino claros"
                        " antes de chamar."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "origin": {
                                "type": "string",
                                "description": "Nome da estação de origem",
                            },
                            "destination": {
                                "type": "string",
                                "description": "Nome da estação de destino",
                            },
                        },
                        "required": ["origin", "destination"],
                    },
                },
            },
        ]

        if tipo_usuario == "Colaborador":
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": "generate_report",
                        "description": (
                            "Gera relatórios técnicos oficiais em PDF para colaboradores CCR."
                            " Utilize apenas quando o colaborador solicitar explicitamente."
                        ),
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "description": {
                                    "type": "string",
                                    "description": "Descrição detalhada do incidente ou necessidade do relatório.",
                                }
                            },
                            "required": ["description"],
                        },
                    },
                }
            )

        return tools

    async def call(self, name: str, arguments: Dict[str, Any], *, tipo_usuario: str, token: Optional[str]) -> str:
        if name == "search_knowledge":
            query = arguments.get("query", "")
            top_k = int(arguments.get("top_k", 3))
            resultados = await self._knowledge_index.search(query, top_k=top_k)
            return json.dumps({"results": resultados}, ensure_ascii=False)

        if name == "plan_route":
            origem = arguments.get("origin") or arguments.get("origem")
            destino = arguments.get("destination") or arguments.get("destino")
            if not origem or not destino:
                return json.dumps({"error": "Forneça origem e destino válidos."}, ensure_ascii=False)
            try:
                plano = rota_service.plan_route(origem, destino)
                payload = {
                    "origem": plano.origem,
                    "destino": plano.destino,
                    "modo": plano.modo,
                    "caminho": plano.caminho,
                    "baldeacoes": plano.baldeacoes,
                    "texto": plano.formatar(),
                }
                return json.dumps(payload, ensure_ascii=False)
            except ValueError as exc:
                return json.dumps({"error": str(exc)}, ensure_ascii=False)

        if name == "generate_report":
            if tipo_usuario != "Colaborador":
                return json.dumps({"error": "Apenas colaboradores podem gerar relatórios."}, ensure_ascii=False)
            if not token:
                return json.dumps({"error": "Token de autenticação ausente para geração de relatórios."}, ensure_ascii=False)

            descricao = arguments.get("description") or arguments.get("texto")
            if not descricao:
                return json.dumps({"error": "Descreva o que deve constar no relatório."}, ensure_ascii=False)

            resultado = relatorio_service.gerar_relatorio(descricao, tipo_usuario="Colaborador", token=token)
            return json.dumps(resultado, ensure_ascii=False)

        return json.dumps({"error": f"Ferramenta desconhecida: {name}"}, ensure_ascii=False)


class LLMOrchestrator:
    """Coordena a conversa com o modelo via abordagem LLM-first."""

    def __init__(self) -> None:
        self._client = get_async_client()
        self._knowledge_index = KnowledgeIndex(self._client)
        self._tool_registry = ToolRegistry(self._knowledge_index)
        self._sessions: Dict[str, SessionState] = {}

    async def handle_message(
        self,
        session_id: str,
        user_text: str,
        tipo_usuario: str,
        token: Optional[str],
    ) -> AsyncIterator[str]:
        if not user_text or not user_text.strip():
            yield "Não recebi nenhuma mensagem. Poderia repetir?"
            return

        if EMERGENCY_PATTERNS.search(user_text):
            yield self._resposta_emergencia(tipo_usuario)
            return

        if not self._is_transport_topic(user_text):
            aviso = (
                "Posso te ajudar com o transporte público de São Paulo."
                " Me conta qual linha, estação ou serviço do metrô, CPTM ou ônibus você quer saber?"
            )
            yield aviso
            return

        session = self._sessions.setdefault(session_id, SessionState())
        session.append({"role": "user", "content": user_text})

        try:
            async for chunk in self._chat_loop(session, tipo_usuario, token):
                yield chunk
        finally:
            session.prune()

    def _resposta_emergencia(self, tipo_usuario: str) -> str:
        if tipo_usuario == "Colaborador":
            return (
                "Recebi um relato de emergência. Acione imediatamente o CCO e siga o protocolo de segurança."
                " Reforce com o usuário que a segurança da equipe e dos passageiros é prioridade."
            )
        return (
            "Sinto muito pelo ocorrido. Entre em contato com a segurança da CPTM/Metrô ou procure um funcionário"
            " imediatamente. Se necessário, ligue para o 190 ou serviço de emergência local."
        )

    async def _chat_loop(
        self,
        session: SessionState,
        tipo_usuario: str,
        token: Optional[str],
    ) -> AsyncIterator[str]:
        base_messages = self._base_messages(tipo_usuario, token is not None)
        tool_defs = self._tool_registry.list_tools(tipo_usuario)

        # Loop para lidar com chamadas de ferramenta sucessivas
        while True:
            messages = cast(List[ChatCompletionMessageParam], base_messages + session.messages)
            try:
                stream = await self._client.chat.completions.create(  # type: ignore[arg-type,call-arg]
                    model="gpt-4.1",
                    messages=messages,
                    temperature=0.4,
                    stream=True,
                    tools=cast(List[ChatCompletionToolParam], tool_defs),
                    tool_choice="auto",
                )
            except Exception as exc:
                mensagem = (
                    "Enfrentei um problema para falar com o modelo agora."
                    " Tente novamente em instantes ou verifique sua conexão."
                )
                session.append({"role": "assistant", "content": mensagem})
                yield mensagem
                break

            final_text: List[str] = []
            tool_call: Optional[Dict[str, Any]] = None

            async for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if not delta:
                    continue

                if delta.content:
                    trecho = delta.content
                    final_text.append(trecho)
                    yield trecho

                if delta.tool_calls:
                    call_info = delta.tool_calls[0]
                    if tool_call is None:
                        tool_call = {
                            "id": call_info.id or f"call_{len(session.messages)}",
                            "name": "",
                            "arguments": "",
                        }
                    if call_info.function:
                        if call_info.function.name:
                            tool_call["name"] = call_info.function.name
                        if call_info.function.arguments:
                            tool_call["arguments"] += call_info.function.arguments

            if tool_call and tool_call.get("name"):
                # Remove qualquer conteúdo parcial enviado ao usuário, pois não é resposta final
                if final_text:
                    # Não reenvia chunks em caso de tool call; limpa buffer do usuário
                    pass

                session.append(
                    {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": tool_call["id"],
                                "type": "function",
                                "function": {
                                    "name": tool_call["name"],
                                    "arguments": tool_call.get("arguments", ""),
                                },
                            }
                        ],
                    }
                )

                try:
                    args = json.loads(tool_call.get("arguments", "{}") or "{}")
                except json.JSONDecodeError:
                    args = {}
                tool_output = await self._tool_registry.call(
                    tool_call["name"],
                    args,
                    tipo_usuario=tipo_usuario,
                    token=token,
                )

                session.append(
                    {
                        "role": "tool",
                        "name": tool_call["name"],
                        "tool_call_id": tool_call["id"],
                        "content": tool_output,
                    }
                )
                # Continua o loop para permitir cadeia de ferramentas
                continue

            # Sem chamada de ferramenta: resposta final já enviada
            resposta = "".join(final_text).strip()
            if not resposta:
                resposta = "Desculpe, não consegui formular uma resposta no momento."
            session.append({"role": "assistant", "content": resposta})
            break

    def _base_messages(self, tipo_usuario: str, has_token: bool) -> List[Dict[str, str]]:
        perfil = "colaborador" if tipo_usuario == "Colaborador" else "passageiro"
        return [
            {
                "role": "system",
                "content": (
                    "Você é Ceci, assistente virtual do transporte público de São Paulo."
                    " Responda sempre de forma cordial, objetiva e no mesmo idioma do usuário."
                    " Utilize ferramentas quando necessário: planeje rotas precisas, pesquise fatos em search_knowledge"
                    " e gere relatórios somente quando um colaborador solicitar explicitamente."
                    " Nunca responda perguntas que não sejam relacionadas ao transporte público de São Paulo."
                ),
            },
            {
                "role": "system",
                "content": (
                    f"Contexto da sessão: usuário é {perfil}. Token disponível: {'sim' if has_token else 'não'}."
                    " Quando usar search_knowledge, cite as informações de forma natural e referencial."
                    " Se o conteúdo do RAG não for suficiente, explique com transparência."
                    " Se a pergunta parecer fora do transporte público de São Paulo, peça gentilmente que o usuário confirme"
                    " mencionando estação, linha ou serviço antes de recusar."
                ),
            },
        ]

    def _is_transport_topic(self, texto: str) -> bool:
        texto_norm = texto.lower()
        texto_unaccented = unidecode(texto_norm)

        if not texto_unaccented.strip():
            return False

        token_keywords = {
            "metro",
            "cptm",
            "monotrilho",
            "linha",
            "linhas",
            "estacao",
            "estacoes",
            "bilhete",
            "bilhetes",
            "tarifa",
            "tarifas",
            "passagem",
            "passagens",
            "trem",
            "trens",
            "tremmetropolitano",
            "viaquatro",
            "viamobilidade",
            "onibus",
            "terminal",
            "terminais",
            "corredor",
            "corredores",
            "transporte",
            "baldeacao",
            "transferencia",
            "horario",
            "horarios",
            "lotacao",
            "lotacoes",
            "estudante",
            "estudantes",
            "paulista",
            "billete",
            "subway",
            "tube",
        }

        frase_keywords = (
            "bilhete unico",
            "sao paulo",
        )

        tokens_texto = set(re.findall(r"\w+", texto_unaccented))

        if token_keywords & tokens_texto:
            return True

        if any(frase in texto_unaccented for frase in frase_keywords):
            return True

        # reforça com os nomes das estações para evitar falsos positivos
        try:
            estacoes = rota_service.list_all_stations()
        except Exception:
            estacoes = []

        for estacao in estacoes:
            estacao_norm = unidecode(estacao.lower())
            if estacao_norm in texto_unaccented or estacao_norm in tokens_texto:
                return True

        return False
