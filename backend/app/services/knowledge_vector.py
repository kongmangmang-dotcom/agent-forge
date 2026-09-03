"""Milvus vector store for knowledge segments."""

from __future__ import annotations

import logging
import threading
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_connected = False
_ensured_dim: int | None = None


def vector_store_name() -> str:
    name = (settings.vector_store or "postgres").strip().lower()
    return name if name in {"milvus", "postgres"} else "postgres"


def milvus_enabled() -> bool:
    return vector_store_name() == "milvus"


def _connect() -> None:
    global _connected
    if _connected:
        return
    with _lock:
        if _connected:
            return
        from pymilvus import connections

        connections.connect(
            alias="default",
            host=settings.milvus_host.strip() or "127.0.0.1",
            port=str(settings.milvus_port or 19530),
        )
        _connected = True
        logger.info(
            "milvus connected host=%s port=%s",
            settings.milvus_host,
            settings.milvus_port,
        )


def _collection_name() -> str:
    name = (settings.milvus_collection or "agentforge_knowledge_segment").strip()
    return name or "agentforge_knowledge_segment"


def ensure_collection(dim: int) -> Any:
    """Create collection if missing; recreate if dim mismatches."""
    global _ensured_dim
    if dim <= 0:
        raise ValueError("embedding dim must be > 0")
    _connect()
    from pymilvus import (
        Collection,
        CollectionSchema,
        DataType,
        FieldSchema,
        utility,
    )

    name = _collection_name()
    with _lock:
        if utility.has_collection(name):
            col = Collection(name)
            # Find vector field dim
            vec_field = next((f for f in col.schema.fields if f.dtype == DataType.FLOAT_VECTOR), None)
            existing_dim = int(vec_field.params.get("dim", 0)) if vec_field else 0
            if existing_dim and existing_dim != dim:
                logger.warning(
                    "milvus collection dim mismatch existing=%s new=%s; dropping %s",
                    existing_dim,
                    dim,
                    name,
                )
                utility.drop_collection(name)
            else:
                if not col.has_index():
                    col.create_index(
                        field_name="embedding",
                        index_params={
                            "index_type": "IVF_FLAT",
                            "metric_type": "IP",
                            "params": {"nlist": 128},
                        },
                    )
                col.load()
                _ensured_dim = dim
                return col

        fields = [
            FieldSchema(name="id", dtype=DataType.VARCHAR, is_primary=True, max_length=64),
            FieldSchema(name="knowledge_id", dtype=DataType.VARCHAR, max_length=64),
            FieldSchema(name="document_id", dtype=DataType.VARCHAR, max_length=64),
            FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=dim),
        ]
        schema = CollectionSchema(fields=fields, description="AgentForge knowledge segments")
        col = Collection(name=name, schema=schema)
        col.create_index(
            field_name="embedding",
            index_params={
                "index_type": "IVF_FLAT",
                "metric_type": "IP",
                "params": {"nlist": 128},
            },
        )
        col.load()
        _ensured_dim = dim
        logger.info("milvus collection ready name=%s dim=%s", name, dim)
        return col


def upsert_segments(
    rows: list[dict[str, Any]],
) -> None:
    """rows: {id, knowledge_id, document_id, embedding}"""
    if not rows:
        return
    dim = len(rows[0]["embedding"])
    col = ensure_collection(dim)
    ids = [str(r["id"]) for r in rows]
    # delete existing ids first for upsert semantics
    quoted = ", ".join(f'"{i}"' for i in ids)
    try:
        col.delete(expr=f"id in [{quoted}]")
    except Exception:
        pass
    col.insert(
        [
            ids,
            [str(r["knowledge_id"]) for r in rows],
            [str(r["document_id"]) for r in rows],
            [list(map(float, r["embedding"])) for r in rows],
        ]
    )
    col.flush()


def delete_by_ids(ids: list[str]) -> None:
    if not ids:
        return
    _connect()
    from pymilvus import Collection, utility

    name = _collection_name()
    if not utility.has_collection(name):
        return
    col = Collection(name)
    quoted = ", ".join(f'"{i}"' for i in ids)
    col.delete(expr=f"id in [{quoted}]")
    col.flush()


def delete_by_document_id(document_id: str) -> None:
    _connect()
    from pymilvus import Collection, utility

    name = _collection_name()
    if not utility.has_collection(name):
        return
    col = Collection(name)
    col.delete(expr=f'document_id == "{document_id}"')
    col.flush()


def delete_by_knowledge_id(knowledge_id: str) -> None:
    _connect()
    from pymilvus import Collection, utility

    name = _collection_name()
    if not utility.has_collection(name):
        return
    col = Collection(name)
    col.delete(expr=f'knowledge_id == "{knowledge_id}"')
    col.flush()


def search(
    knowledge_id: str,
    query_vector: list[float],
    top_k: int,
) -> list[tuple[str, float]]:
    """Return list of (segment_id, score) sorted by score desc."""
    if not query_vector:
        return []
    col = ensure_collection(len(query_vector))
    col.load()
    results = col.search(
        data=[list(map(float, query_vector))],
        anns_field="embedding",
        param={"metric_type": "IP", "params": {"nprobe": 16}},
        limit=max(1, top_k),
        expr=f'knowledge_id == "{knowledge_id}"',
        output_fields=["id"],
    )
    out: list[tuple[str, float]] = []
    if not results:
        return out
    for hit in results[0]:
        sid = hit.id if hasattr(hit, "id") else hit.entity.get("id")
        score = float(hit.score)
        out.append((str(sid), score))
    return out
