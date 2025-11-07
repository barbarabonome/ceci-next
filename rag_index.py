"""Gerenciamento de índice RAG usando embeddings da OpenAI."""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

from openai import AsyncOpenAI


@dataclass
class KnowledgeDocument:
    doc_id: str
    text: str
    metadata: Dict[str, str]


class KnowledgeIndex:
    """Mantém um índice local de embeddings e utiliza OpenAI para expansão."""

    def __init__(
        self,
        client: AsyncOpenAI,
        cache_path: Path | str = Path(".cache/rag_index.json"),
        embedding_model: str = "text-embedding-3-large",
    ) -> None:
        self._client = client
        self._cache_path = Path(cache_path)
        self._embedding_model = embedding_model
        self._documents: List[KnowledgeDocument] = self._load_documents()
        self._embeddings: Optional[List[List[float]]] = None
        self._data_hash = self._compute_hash(self._documents)
        self._lock = asyncio.Lock()

    async def ensure_ready(self) -> None:
        async with self._lock:
            if self._embeddings is not None:
                return

            cached = self._read_cache()
            if cached and cached.get("hash") == self._data_hash:
                self._embeddings = cached["embeddings"]
                return

            self._embeddings = await self._embed_documents(self._documents)
            self._write_cache({
                "hash": self._data_hash,
                "embeddings": self._embeddings,
                "documents": [doc.__dict__ for doc in self._documents],
                "embedding_model": self._embedding_model,
            })

    async def search(self, query: str, top_k: int = 3) -> List[Dict[str, str]]:
        await self.ensure_ready()
        if not query.strip():
            return []

        query_embedding = await self._embed_text(query)
        scored = []
        assert self._embeddings is not None
        for doc, emb in zip(self._documents, self._embeddings):
            score = self._cosine_similarity(query_embedding, emb)
            scored.append((score, doc))

        scored.sort(key=lambda item: item[0], reverse=True)
        resultados = []
        for score, doc in scored[: max(1, top_k)]:
            resultados.append({
                "doc_id": doc.doc_id,
                "score": round(score, 4),
                "text": doc.text,
                "metadata": doc.metadata,
            })
        return resultados

    def _load_documents(self) -> List[KnowledgeDocument]:
        docs: List[KnowledgeDocument] = []
        base_path = Path("data")

        def add_doc(doc_id: str, text: str, metadata: Optional[Dict[str, str]] = None) -> None:
            docs.append(
                KnowledgeDocument(
                    doc_id=doc_id,
                    text=text.strip(),
                    metadata=metadata or {},
                )
            )

        faq_ccr_path = base_path / "faq_ccr.json"
        if faq_ccr_path.exists():
            data = json.loads(faq_ccr_path.read_text(encoding="utf-8"))
            faqs = self._extract_list(data, "faqs_colaborador")
            for idx, faq in enumerate(faqs):
                pergunta = faq.get("question") or faq.get("pergunta") or ""
                resposta = faq.get("answer") or faq.get("resposta") or ""
                add_doc(
                    f"faq_colaborador_{idx}",
                    f"Pergunta do colaborador: {pergunta}\nResposta: {resposta}",
                    {"tipo": "faq_colaborador"},
                )

        faq_passageiro_path = base_path / "faq_passageiro.json"
        if faq_passageiro_path.exists():
            data = json.loads(faq_passageiro_path.read_text(encoding="utf-8"))
            faqs = self._extract_list(data, "faqs_passageiro")
            for idx, faq in enumerate(faqs):
                pergunta = faq.get("question") or faq.get("pergunta") or ""
                resposta = faq.get("answer") or faq.get("resposta") or ""
                add_doc(
                    f"faq_passageiro_{idx}",
                    f"Pergunta do passageiro: {pergunta}\nResposta: {resposta}",
                    {"tipo": "faq_passageiro"},
                )

        linhas_path = base_path / "data_linhas.json"
        if linhas_path.exists():
            linhas = json.loads(linhas_path.read_text(encoding="utf-8")).get("linhas", [])
            for idx, linha in enumerate(linhas):
                nome = linha.get("nome", "Linha")
                operadora = linha.get("operadora", "")
                estacoes = ", ".join(linha.get("estacoes", [])[:40])
                texto = (
                    f"Linha {nome} (operadora: {operadora}). Esta linha atende as estações: {estacoes}."
                )
                add_doc(f"linha_{idx}", texto, {"tipo": "linha", "linha": nome})

        return docs

    async def _embed_documents(self, docs: Sequence[KnowledgeDocument]) -> List[List[float]]:
        textos = [doc.text for doc in docs]
        embeddings: List[List[float]] = []

        # Cria diretório de cache, se necessário
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)

        batch_size = 32
        for start in range(0, len(textos), batch_size):
            batch = textos[start : start + batch_size]
            response = await self._client.embeddings.create(
                model=self._embedding_model,
                input=batch,
            )
            embeddings.extend([item.embedding for item in response.data])
        return embeddings

    async def _embed_text(self, text: str) -> List[float]:
        response = await self._client.embeddings.create(
            model=self._embedding_model,
            input=text,
        )
        return response.data[0].embedding

    @staticmethod
    def _compute_hash(documents: Iterable[KnowledgeDocument]) -> str:
        payload = [doc.__dict__ for doc in documents]
        blob = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
        return hashlib.sha256(blob).hexdigest()

    def _read_cache(self) -> Optional[Dict]:
        if not self._cache_path.exists():
            return None
        try:
            return json.loads(self._cache_path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def _write_cache(self, data: Dict) -> None:
        tmp_path = self._cache_path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        tmp_path.replace(self._cache_path)

    @staticmethod
    def _cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a)) or 1.0
        norm_b = math.sqrt(sum(x * x for x in b)) or 1.0
        return dot / (norm_a * norm_b)

    @staticmethod
    def _extract_list(data: Dict, key: str) -> List[Dict]:
        if key in data and isinstance(data[key], list):
            return data[key]
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and key in item and isinstance(item[key], list):
                    return item[key]
        return []
