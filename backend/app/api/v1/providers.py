from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.schemas.common import ListResponse
from app.schemas.provider import ProviderCreate, ProviderRead, ProviderTestResult, ProviderUpdate
from app.services.provider_service import ProviderService

router = APIRouter(prefix="/providers", tags=["providers"])


@router.get("", response_model=ListResponse[ProviderRead])
async def list_providers(db: AsyncSession = Depends(get_session)):
    items = await ProviderService(db).list_providers()
    return {"items": items}


@router.post("", response_model=ProviderRead, status_code=201)
async def create_provider(body: ProviderCreate, db: AsyncSession = Depends(get_session)):
    return await ProviderService(db).create_provider(body)


@router.get("/{provider_id}", response_model=ProviderRead)
async def get_provider(provider_id: str, db: AsyncSession = Depends(get_session)):
    return await ProviderService(db).get_provider(provider_id)


@router.patch("/{provider_id}", response_model=ProviderRead)
async def update_provider(
    provider_id: str, body: ProviderUpdate, db: AsyncSession = Depends(get_session)
):
    return await ProviderService(db).update_provider(provider_id, body)


@router.delete("/{provider_id}", status_code=204)
async def delete_provider(provider_id: str, db: AsyncSession = Depends(get_session)):
    await ProviderService(db).delete_provider(provider_id)


@router.post("/{provider_id}/test", response_model=ProviderTestResult)
async def test_provider(provider_id: str, db: AsyncSession = Depends(get_session)):
    ok, message, latency = await ProviderService(db).test_connection(provider_id)
    return ProviderTestResult(ok=ok, provider_id=provider_id, message=message, latency_ms=latency)
