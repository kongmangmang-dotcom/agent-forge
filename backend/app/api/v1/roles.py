from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.schemas.common import ListResponse
from app.schemas.role import RoleCreate, RoleRead, RoleUpdate
from app.services.role_service import RoleService

router = APIRouter(prefix="/roles", tags=["roles"])


@router.get("", response_model=ListResponse[RoleRead])
async def list_roles(db: AsyncSession = Depends(get_session)):
    items = await RoleService(db).list_roles()
    return {"items": items}


@router.post("", response_model=RoleRead, status_code=201)
async def create_role(body: RoleCreate, db: AsyncSession = Depends(get_session)):
    return await RoleService(db).create_role(body)


@router.get("/{role_id}", response_model=RoleRead)
async def get_role(role_id: str, db: AsyncSession = Depends(get_session)):
    return await RoleService(db).get_role(role_id)


@router.patch("/{role_id}", response_model=RoleRead)
async def update_role(
    role_id: str, body: RoleUpdate, db: AsyncSession = Depends(get_session)
):
    return await RoleService(db).update_role(role_id, body)


@router.delete("/{role_id}", status_code=204)
async def delete_role(role_id: str, db: AsyncSession = Depends(get_session)):
    await RoleService(db).delete_role(role_id)
