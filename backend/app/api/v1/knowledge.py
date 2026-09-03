from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.core.exceptions import ValidationError
from app.schemas.common import ListResponse
from app.schemas.knowledge import (
    KnowledgeBaseCreate,
    KnowledgeBaseRead,
    KnowledgeBaseUpdate,
    KnowledgeChatRequest,
    KnowledgeChatResponse,
    KnowledgeDocumentCreate,
    KnowledgeDocumentDetail,
    KnowledgeDocumentRead,
    KnowledgeDocumentsFromNotes,
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
    KnowledgeSegmentRead,
)
from app.services.knowledge_service import KnowledgeService

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


@router.get("/bases", response_model=ListResponse[KnowledgeBaseRead])
async def list_bases(db: AsyncSession = Depends(get_session)):
    items = await KnowledgeService(db).list_bases()
    return {"items": items}


@router.post("/bases", response_model=KnowledgeBaseRead, status_code=201)
async def create_base(body: KnowledgeBaseCreate, db: AsyncSession = Depends(get_session)):
    return await KnowledgeService(db).create_base(body)


@router.get("/bases/{knowledge_id}", response_model=KnowledgeBaseRead)
async def get_base(knowledge_id: str, db: AsyncSession = Depends(get_session)):
    return await KnowledgeService(db).get_base(knowledge_id)


@router.patch("/bases/{knowledge_id}", response_model=KnowledgeBaseRead)
async def update_base(
    knowledge_id: str, body: KnowledgeBaseUpdate, db: AsyncSession = Depends(get_session)
):
    return await KnowledgeService(db).update_base(knowledge_id, body)


@router.delete("/bases/{knowledge_id}", status_code=204)
async def delete_base(knowledge_id: str, db: AsyncSession = Depends(get_session)):
    await KnowledgeService(db).delete_base(knowledge_id)


@router.post("/bases/{knowledge_id}/reindex", response_model=KnowledgeBaseRead)
async def reindex_base(knowledge_id: str, db: AsyncSession = Depends(get_session)):
    return await KnowledgeService(db).reindex_base(knowledge_id)


@router.post("/bases/{knowledge_id}/search", response_model=KnowledgeSearchResponse)
async def search_base(
    knowledge_id: str, body: KnowledgeSearchRequest, db: AsyncSession = Depends(get_session)
):
    return await KnowledgeService(db).search(knowledge_id, body)


@router.post("/bases/{knowledge_id}/chat", response_model=KnowledgeChatResponse)
async def chat_base(
    knowledge_id: str, body: KnowledgeChatRequest, db: AsyncSession = Depends(get_session)
):
    return await KnowledgeService(db).chat(knowledge_id, body)


@router.get(
    "/bases/{knowledge_id}/documents",
    response_model=ListResponse[KnowledgeDocumentRead],
)
async def list_documents(knowledge_id: str, db: AsyncSession = Depends(get_session)):
    items = await KnowledgeService(db).list_documents(knowledge_id)
    return {"items": items}


@router.post(
    "/bases/{knowledge_id}/documents",
    response_model=KnowledgeDocumentRead,
    status_code=201,
)
async def create_document(
    knowledge_id: str,
    body: KnowledgeDocumentCreate,
    db: AsyncSession = Depends(get_session),
):
    return await KnowledgeService(db).create_document(knowledge_id, body)


@router.post(
    "/bases/{knowledge_id}/documents/upload",
    response_model=KnowledgeDocumentRead,
    status_code=201,
)
async def upload_document(
    knowledge_id: str,
    file: UploadFile = File(...),
    segment_max_chars: int = Form(default=800),
    db: AsyncSession = Depends(get_session),
):
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="空文件")
    name = file.filename or "upload.bin"
    try:
        return await KnowledgeService(db).create_document_from_upload(
            knowledge_id,
            filename=name,
            data=raw,
            segment_max_chars=max(100, min(8000, int(segment_max_chars))),
        )
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/bases/{knowledge_id}/documents/from-notes",
    response_model=ListResponse[KnowledgeDocumentRead],
    status_code=201,
)
async def create_documents_from_notes(
    knowledge_id: str,
    body: KnowledgeDocumentsFromNotes,
    db: AsyncSession = Depends(get_session),
):
    items = await KnowledgeService(db).create_documents_from_notes(knowledge_id, body)
    return {"items": items}


@router.get("/documents/{document_id}", response_model=KnowledgeDocumentDetail)
async def get_document(document_id: str, db: AsyncSession = Depends(get_session)):
    return await KnowledgeService(db).get_document(document_id)


@router.delete("/documents/{document_id}", status_code=204)
async def delete_document(document_id: str, db: AsyncSession = Depends(get_session)):
    await KnowledgeService(db).delete_document(document_id)


@router.get(
    "/documents/{document_id}/segments",
    response_model=ListResponse[KnowledgeSegmentRead],
)
async def list_segments(document_id: str, db: AsyncSession = Depends(get_session)):
    items = await KnowledgeService(db).list_segments(document_id)
    return {"items": items}
