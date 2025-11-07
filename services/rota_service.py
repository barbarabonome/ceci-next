"""Serviços de cálculo de rota para a assistente Ceci."""

from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass
from difflib import get_close_matches
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import networkx as nx
import requests


DATA_FILE = Path("data/data_linhas.json")
TEMPO_BASE = 3


def _normalize(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto or "").encode("ASCII", "ignore").decode("ASCII").casefold()


@lru_cache(maxsize=1)
def _load_data() -> Dict:
    with DATA_FILE.open("r", encoding="utf-8") as fh:
        return json.load(fh)


@lru_cache(maxsize=1)
def _build_graph() -> nx.Graph:
    dados = _load_data()
    graph = nx.Graph()

    for linha in dados.get("linhas", []):
        nome_linha = linha.get("nome")
        estacoes = linha.get("estacoes", [])
        operadora = linha.get("operadora")

        for a, b in zip(estacoes[:-1], estacoes[1:]):
            graph.add_edge(
                a,
                b,
                tempo=TEMPO_BASE,
                linha=nome_linha,
                operadora=operadora,
            )

    for estacao in list(graph.nodes):
        linhas_encontradas = [
            linha.get("nome")
            for linha in dados.get("linhas", [])
            if estacao in linha.get("estacoes", [])
        ]
        if len(linhas_encontradas) > 1:
            graph.nodes[estacao]["baldeacoes"] = linhas_encontradas

    return graph


@lru_cache(maxsize=1)
def _fetch_status() -> Dict[str, str]:
    status_operacao: Dict[str, str] = {}
    try:
        resp = requests.get(
            "https://www.diretodostrens.com.br/api/status",
            timeout=5,
            verify=False,
        )
        resp.raise_for_status()
        for item in resp.json():
            nome = _normalize(item.get("nome", ""))
            status_operacao[nome] = item.get("situacao", "").strip()
    except Exception:
        # Silencia falhas de rede para não derrubar o cálculo de rota
        pass
    return status_operacao


@lru_cache(maxsize=1)
def list_all_stations() -> List[str]:
    dados = _load_data()
    estacoes = [est for linha in dados.get("linhas", []) for est in linha.get("estacoes", [])]
    return sorted(set(estacoes))


def _calcular_peso(u: str, v: str, modo: str = "rapido") -> float:
    graph = _build_graph()
    atributos = graph.get_edge_data(u, v) or {}
    tempo = atributos.get("tempo", TEMPO_BASE)

    linha = atributos.get("linha", "")
    situacao = _fetch_status().get(_normalize(linha), "").lower()
    if any(p in situacao for p in ("reduzida", "falha", "interrup")):
        tempo += 10

    if modo == "simples" and graph.nodes[u].get("baldeacoes"):
        tempo += 3
    elif modo == "acessivel":
        tempo += 2

    return tempo


def _custo_total(caminho: List[str], modo: str) -> float:
    total = 0.0
    for u, v in zip(caminho[:-1], caminho[1:]):
        total += _calcular_peso(u, v, modo)
    return total


def _detectar_baldeacoes(caminho: List[str]) -> List[Tuple[str, str, str]]:
    graph = _build_graph()
    segmentos = [
        (u, v, graph.get_edge_data(u, v) or {})
        for u, v in zip(caminho[:-1], caminho[1:])
    ]

    baldeacoes: List[Tuple[str, str, str]] = []
    linhas_previas: List[str] = []

    for idx, (_, _, dados) in enumerate(segmentos):
        linha_atual = dados.get("linha", "")
        linhas_previas.append(linha_atual)
        if idx == 0:
            continue
        if linha_atual != linhas_previas[idx - 1]:
            baldeacoes.append((caminho[idx], linhas_previas[idx - 1], linha_atual))

    return baldeacoes


def _resolver_estacao(nome: str) -> Optional[str]:
    if not nome:
        return None

    estacoes = list_all_stations()
    normalizado = _normalize(nome)
    mapa_normalizado = { _normalize(est): est for est in estacoes }

    if normalizado in mapa_normalizado:
        return mapa_normalizado[normalizado]

    candidatos = get_close_matches(normalizado, mapa_normalizado.keys(), n=1, cutoff=0.8)
    if candidatos:
        return mapa_normalizado[candidatos[0]]
    return None


@dataclass
class RoutePlan:
    origem: str
    destino: str
    modo: str
    caminho: List[str]
    custo_estimado: float
    baldeacoes: List[Tuple[str, str, str]]

    def formatar(self) -> str:
        minutos = max(int(round(self.custo_estimado)), len(self.caminho) - 1)
        if self.baldeacoes:
            linhas = [f"🚇 De {self.origem} para {self.destino} (~{minutos} min):"]
            for est, antiga, nova in self.baldeacoes:
                linhas.append(f"   • Troque em {est}: {antiga} → {nova}")
            return "\n".join(linhas)

        return f"🚇 De {self.origem} para {self.destino} (~{minutos} min) - Linha direta"


def plan_route(origem: str, destino: str) -> RoutePlan:
    origem_resolvida = _resolver_estacao(origem)
    destino_resolvido = _resolver_estacao(destino)

    if not origem_resolvida or not destino_resolvido:
        raise ValueError("Não consegui identificar a estação de origem ou destino informado.")

    graph = _build_graph()
    modos = ("rapido", "simples", "acessivel")
    melhores: Dict[str, RoutePlan] = {}

    for modo in modos:
        try:
            if modo == "simples":
                caminho = nx.dijkstra_path(
                    graph,
                    origem_resolvida,
                    destino_resolvido,
                    weight=lambda u, v, _: _calcular_peso(u, v, modo),
                )
            else:
                caminho = nx.astar_path(
                    graph,
                    origem_resolvida,
                    destino_resolvido,
                    heuristic=lambda u, v: TEMPO_BASE * (len(nx.shortest_path(graph, u, v)) - 1),
                    weight=lambda u, v, _: _calcular_peso(u, v, modo),
                )

            custo = _custo_total(caminho, modo)
            melhores[modo] = RoutePlan(
                origem=origem_resolvida,
                destino=destino_resolvido,
                modo=modo,
                caminho=caminho,
                custo_estimado=custo,
                baldeacoes=_detectar_baldeacoes(caminho),
            )
        except nx.NetworkXNoPath:
            continue

    if not melhores:
        raise ValueError(f"Não há rota disponível de {origem_resolvida} até {destino_resolvido}.")

    melhor = min(melhores.values(), key=lambda plano: plano.custo_estimado)
    return melhor


def describe_route(origem: str, destino: str) -> str:
    plano = plan_route(origem, destino)
    return plano.formatar()