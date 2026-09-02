from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.schemas.agent import AgentCreate, AgentRead, AgentUpdate, RoleTemplate
from app.schemas.common import ListResponse
from app.services.agent_service import AgentService
from app.services.role_service import RoleService

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("", response_model=ListResponse[AgentRead])
async def list_agents(db: AsyncSession = Depends(get_session)):
    items = await AgentService(db).list_agents()
    return {"items": items}


@router.post("", response_model=AgentRead, status_code=201)
async def create_agent(body: AgentCreate, db: AsyncSession = Depends(get_session)):
    return await AgentService(db).create_agent(body)


@router.get("/roles/templates", response_model=ListResponse[RoleTemplate])
async def role_templates(db: AsyncSession = Depends(get_session)):
    """兼容旧前端：从 agent_role 表读取。"""
    roles = await RoleService(db).list_roles()
    return {
        "items": [
            RoleTemplate(
                role=r.code,
                label=r.name,
                desc=r.description,
                default_provider_kind=r.default_provider_kind,
            )
            for r in roles
        ]
    }


@router.get("/{agent_id}", response_model=AgentRead)
async def get_agent(agent_id: str, db: AsyncSession = Depends(get_session)):
    return await AgentService(db).get_agent(agent_id)


@router.patch("/{agent_id}", response_model=AgentRead)
async def update_agent(
    agent_id: str, body: AgentUpdate, db: AsyncSession = Depends(get_session)
):
    return await AgentService(db).update_agent(agent_id, body)


@router.delete("/{agent_id}", status_code=204)
async def delete_agent(agent_id: str, db: AsyncSession = Depends(get_session)):
    await AgentService(db).delete_agent(agent_id)
