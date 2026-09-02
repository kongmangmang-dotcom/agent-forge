from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.core.ids import new_id
from app.models.knowledge import (
    KnowledgeBaseModel,
    KnowledgeDocumentModel,
    KnowledgeSegmentModel,
)
from app.schemas.knowledge import (
    KnowledgeBaseCreate,
    KnowledgeBaseRead,
    KnowledgeBaseUpdate,
    KnowledgeChatRequest,
    KnowledgeChatResponse,
    KnowledgeDocumentCreate,
    KnowledgeDocumentDetail,
    KnowledgeDocumentRead,
    KnowledgeSearchHit,
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
    KnowledgeSegmentRead,
)
from app.services.knowledge_chunk import chunk_text
from app.services.knowledge_chat import chat_backend_name, chat_complete
from app.services.knowledge_embed import (
    cosine_similarity,
    default_embedding_model,
    embed_query,
    embed_texts,
    embedding_backend_name,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class KnowledgeService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_bases(self) -> list[KnowledgeBaseRead]:
        result = await self.db.execute(
            select(KnowledgeBaseModel).order_by(KnowledgeBaseModel.created_at.desc())
        )
        rows = result.scalars().all()
        out: list[KnowledgeBaseRead] = []
        for row in rows:
            out.append(await self._base_to_read(row))
        return out

    async def create_base(self, data: KnowledgeBaseCreate) -> KnowledgeBaseRead:
        name = data.name.strip()
        if not name:
            raise ValidationError("知识库名称不能为空")
        row = KnowledgeBaseModel(
            id=new_id("kb"),
            name=name,
            description=(data.description or "").strip(),
            embedding_model=(data.embedding_model or default_embedding_model()).strip(),
            top_k=data.top_k,
            similarity_threshold=data.similarity_threshold,
            status="active",
        )
        self.db.add(row)
        await self.db.commit()
        await self.db.refresh(row)
        return await self._base_to_read(row)

    async def get_base(self, knowledge_id: str) -> KnowledgeBaseRead:
        row = await self._get_base_row(knowledge_id)
        return await self._base_to_read(row)

    async def update_base(self, knowledge_id: str, data: KnowledgeBaseUpdate) -> KnowledgeBaseRead:
        row = await self._get_base_row(knowledge_id)
        updates = data.model_dump(exclude_unset=True)
        reindex = False
        if "embedding_model" in updates and updates["embedding_model"] is not None:
            new_model = str(updates["embedding_model"]).strip() or default_embedding_model()
            if new_model != row.embedding_model:
                reindex = True
            updates["embedding_model"] = new_model
        if "name" in updates and updates["name"] is not None:
            updates["name"] = str(updates["name"]).strip()
            if not updates["name"]:
                raise ValidationError("知识库名称不能为空")
        if "status" in updates and updates["status"] not in (None, "active", "disabled"):
            raise ValidationError("status 需为 active|disabled")
        for key, value in updates.items():
            setattr(row, key, value)
        row.updated_at = _now()
        await self.db.commit()
        if reindex:
            await self.reindex_base(knowledge_id)
            row = await self._get_base_row(knowledge_id)
        else:
            await self.db.refresh(row)
        return await self._base_to_read(row)

    async def delete_base(self, knowledge_id: str) -> None:
        row = await self._get_base_row(knowledge_id)
        await self.db.delete(row)
        await self.db.commit()

    async def list_documents(self, knowledge_id: str) -> list[KnowledgeDocumentRead]:
        await self._get_base_row(knowledge_id)
        result = await self.db.execute(
            select(KnowledgeDocumentModel)
            .where(KnowledgeDocumentModel.knowledge_id == knowledge_id)
            .order_by(KnowledgeDocumentModel.created_at.desc())
        )
        docs = result.scalars().all()
        out: list[KnowledgeDocumentRead] = []
        for doc in docs:
            out.append(await self._doc_to_read(doc))
        return out

    async def create_document(
        self, knowledge_id: str, data: KnowledgeDocumentCreate
    ) -> KnowledgeDocumentRead:
        base = await self._get_base_row(knowledge_id)
        content = data.content.strip()
        if not content:
            raise ValidationError("文档内容不能为空")
        doc = KnowledgeDocumentModel(
            id=new_id("kdoc"),
            knowledge_id=base.id,
            name=data.name.strip(),
            content=content,
            content_length=len(content),
            segment_max_chars=data.segment_max_chars,
            status="indexing",
        )
        self.db.add(doc)
        await self.db.flush()
        await self._rebuild_segments(base, doc)
        doc.status = "indexed"
        doc.updated_at = _now()
        await self.db.commit()
        await self.db.refresh(doc)
        return await self._doc_to_read(doc)

    async def get_document(self, document_id: str) -> KnowledgeDocumentDetail:
        doc = await self._get_doc_row(document_id)
        read = await self._doc_to_read(doc)
        return KnowledgeDocumentDetail(**read.model_dump(), content=doc.content)

    async def delete_document(self, document_id: str) -> None:
        doc = await self._get_doc_row(document_id)
        await self.db.delete(doc)
        await self.db.commit()

    async def list_segments(self, document_id: str) -> list[KnowledgeSegmentRead]:
        await self._get_doc_row(document_id)
        result = await self.db.execute(
            select(KnowledgeSegmentModel)
            .where(KnowledgeSegmentModel.document_id == document_id)
            .order_by(KnowledgeSegmentModel.created_at.asc())
        )
        return [
            KnowledgeSegmentRead(
                id=s.id,
                knowledge_id=s.knowledge_id,
                document_id=s.document_id,
                content=s.content,
                content_length=s.content_length,
                status=s.status,
                created_at=s.created_at,
                updated_at=s.updated_at,
            )
            for s in result.scalars().all()
        ]

    async def reindex_base(self, knowledge_id: str) -> KnowledgeBaseRead:
        base = await self._get_base_row(knowledge_id)
        result = await self.db.execute(
            select(KnowledgeDocumentModel).where(
                KnowledgeDocumentModel.knowledge_id == knowledge_id
            )
        )
        docs = result.scalars().all()
        for doc in docs:
            doc.status = "indexing"
            await self._rebuild_segments(base, doc)
            doc.status = "indexed"
            doc.updated_at = _now()
        await self.db.commit()
        return await self._base_to_read(base)

    async def search(
        self, knowledge_id: str, data: KnowledgeSearchRequest
    ) -> KnowledgeSearchResponse:
        base = await self._get_base_row(knowledge_id)
        query = data.query.strip()
        if not query:
            raise ValidationError("查询不能为空")
        top_k = data.top_k or base.top_k
        threshold = (
            data.similarity_threshold
            if data.similarity_threshold is not None
            else base.similarity_threshold
        )

        qvec = await embed_query(query, model=base.embedding_model or None)
        result = await self.db.execute(
            select(KnowledgeSegmentModel, KnowledgeDocumentModel.name)
            .join(
                KnowledgeDocumentModel,
                KnowledgeDocumentModel.id == KnowledgeSegmentModel.document_id,
            )
            .where(
                KnowledgeSegmentModel.knowledge_id == knowledge_id,
                KnowledgeSegmentModel.status == "active",
            )
        )
        scored: list[KnowledgeSearchHit] = []
        for seg, doc_name in result.all():
            emb = seg.embedding
            if not isinstance(emb, list) or not emb:
                continue
            score = cosine_similarity(qvec, [float(x) for x in emb])
            if score < threshold:
                continue
            scored.append(
                KnowledgeSearchHit(
                    segment_id=seg.id,
                    document_id=seg.document_id,
                    document_name=doc_name,
                    content=seg.content,
                    score=round(score, 6),
                )
            )
        scored.sort(key=lambda h: h.score, reverse=True)
        return KnowledgeSearchResponse(
            items=scored[:top_k],
            embedding_backend=embedding_backend_name(),
        )

    async def chat(
        self, knowledge_id: str, data: KnowledgeChatRequest
    ) -> KnowledgeChatResponse:
        message = data.message.strip()
        if not message:
            raise ValidationError("问题不能为空")

        search = await self.search(
            knowledge_id,
            KnowledgeSearchRequest(
                query=message,
                top_k=data.top_k,
                similarity_threshold=data.similarity_threshold,
            ),
        )
        citations = search.items
        backend = chat_backend_name()

        if not citations:
            answer = "知识库中没有检索到相关内容。可以先在「文件」里添加文档，或换个问法再试。"
            return KnowledgeChatResponse(
                answer=answer,
                citations=[],
                chat_backend=backend,
                embedding_backend=search.embedding_backend,
            )

        if backend == "openai_compatible":
            context_blocks = []
            for i, hit in enumerate(citations, start=1):
                context_blocks.append(
                    f"[{i}] 来源: {hit.document_name}\n{hit.content}"
                )
            context = "\n\n".join(context_blocks)
            system = (
                "你是知识库问答助手。只依据提供的检索片段回答用户问题；"
                "若片段不足请明确说明不知道。回答简洁，必要时引用 [编号]。"
            )
            hist_lines = []
            for m in data.history[-6:]:
                role = "用户" if m.role == "user" else "助手"
                hist_lines.append(f"{role}: {m.content.strip()}")
            history_text = "\n".join(hist_lines)
            user_prompt = (
                f"检索片段：\n{context}\n\n"
                + (f"近期对话：\n{history_text}\n\n" if history_text else "")
                + f"用户问题：{message}"
            )
            try:
                answer = await chat_complete(system, user_prompt)
            except ValidationError:
                answer = self._extractive_answer(message, citations)
                backend = "extractive_fallback"
        else:
            answer = self._extractive_answer(message, citations)

        return KnowledgeChatResponse(
            answer=answer,
            citations=citations,
            chat_backend=backend,
            embedding_backend=search.embedding_backend,
        )

    @staticmethod
    def _extractive_answer(question: str, citations: list[KnowledgeSearchHit]) -> str:
        lines = [
            f"根据知识库检索（未配置 Chat API，返回摘录整理）：",
            "",
        ]
        for i, hit in enumerate(citations[:5], start=1):
            snippet = hit.content.strip()
            if len(snippet) > 420:
                snippet = snippet[:420] + "…"
            lines.append(f"**[{i}] {hit.document_name}**（相关度 {hit.score:.3f}）")
            lines.append(snippet)
            lines.append("")
        lines.append(f"问题：{question}")
        lines.append("若要合成自然语言回答，请配置 CHAT_API_URL / CHAT_API_KEY。")
        return "\n".join(lines).strip()

    async def _rebuild_segments(
        self, base: KnowledgeBaseModel, doc: KnowledgeDocumentModel
    ) -> None:
        existing = await self.db.execute(
            select(KnowledgeSegmentModel).where(KnowledgeSegmentModel.document_id == doc.id)
        )
        for old in existing.scalars().all():
            await self.db.delete(old)
        await self.db.flush()

        pieces = chunk_text(doc.content, max_chars=doc.segment_max_chars)
        if not pieces:
            return
        vectors = await embed_texts(pieces, model=base.embedding_model or None)
        for text, emb in zip(pieces, vectors):
            self.db.add(
                KnowledgeSegmentModel(
                    id=new_id("kseg"),
                    knowledge_id=base.id,
                    document_id=doc.id,
                    content=text,
                    content_length=len(text),
                    embedding=emb,
                    status="active",
                )
            )
        await self.db.flush()

    async def _get_base_row(self, knowledge_id: str) -> KnowledgeBaseModel:
        row = await self.db.get(KnowledgeBaseModel, knowledge_id)
        if not row:
            raise NotFoundError("KnowledgeBase", knowledge_id)
        return row

    async def _get_doc_row(self, document_id: str) -> KnowledgeDocumentModel:
        row = await self.db.get(KnowledgeDocumentModel, document_id)
        if not row:
            raise NotFoundError("KnowledgeDocument", document_id)
        return row

    async def _base_to_read(self, row: KnowledgeBaseModel) -> KnowledgeBaseRead:
        doc_count = await self.db.scalar(
            select(func.count())
            .select_from(KnowledgeDocumentModel)
            .where(KnowledgeDocumentModel.knowledge_id == row.id)
        )
        seg_count = await self.db.scalar(
            select(func.count())
            .select_from(KnowledgeSegmentModel)
            .where(KnowledgeSegmentModel.knowledge_id == row.id)
        )
        return KnowledgeBaseRead(
            id=row.id,
            name=row.name,
            description=row.description or "",
            embedding_model=row.embedding_model or "",
            top_k=row.top_k,
            similarity_threshold=row.similarity_threshold,
            status=row.status,
            document_count=int(doc_count or 0),
            segment_count=int(seg_count or 0),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    async def _doc_to_read(self, doc: KnowledgeDocumentModel) -> KnowledgeDocumentRead:
        seg_count = await self.db.scalar(
            select(func.count())
            .select_from(KnowledgeSegmentModel)
            .where(KnowledgeSegmentModel.document_id == doc.id)
        )
        return KnowledgeDocumentRead(
            id=doc.id,
            knowledge_id=doc.knowledge_id,
            name=doc.name,
            content_length=doc.content_length,
            segment_max_chars=doc.segment_max_chars,
            status=doc.status,
            segment_count=int(seg_count or 0),
            created_at=doc.created_at,
            updated_at=doc.updated_at,
        )
