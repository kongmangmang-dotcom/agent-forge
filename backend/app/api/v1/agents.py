from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.schemas.agent import AgentCreate, AgentRead, AgentUpdate, RoleTemplate
from app.schemas.common import ListResponse
from app.services.agent_service import AgentService

router = APIRouter(prefix="/agents", tags=["agents"])

ROLE_TEMPLATES: list[RoleTemplate] = [
    RoleTemplate(
        role="planner",
        label="Planner",
        desc="理解需求、拆分任务、建立依赖、制定验收标准",
        default_provider_kind="openai",
    ),
    RoleTemplate(
        role="researcher",
        label="Researcher",
        desc="阅读项目结构、分析代码、查找风险",
        default_provider_kind="anthropic",
    ),
    RoleTemplate(
        role="developer",
        label="Developer",
        desc="编写代码、修改文件、修复问题",
        default_provider_kind="codex_cli",
    ),
    RoleTemplate(
        role="tester",
        label="Tester",
        desc="编写测试、执行测试、分析失败原因",
        default_provider_kind="opencode_cli",
    ),
    RoleTemplate(
        role="reviewer",
        label="Reviewer",
        desc="检查功能完整性、代码质量、安全问题",
        default_provider_kind="gemini",
    ),
    RoleTemplate(
        role="integrator",
        label="Integrator",
        desc="合并代码、解决冲突、最终验证",
        default_provider_kind="codex_cli",
    ),
]


@router.get("", response_model=ListResponse[AgentRead])
async def list_agents(db: AsyncSession = Depends(get_session)):
    items = await AgentService(db).list_agents()
    return {"items": items}


@router.post("", response_model=AgentRead, status_code=201)
async def create_agent(body: AgentCreate, db: AsyncSession = Depends(get_session)):
    return await AgentService(db).create_agent(body)


@router.get("/roles/templates", response_model=ListResponse[RoleTemplate])
async def role_templates():
    return {"items": ROLE_TEMPLATES}


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
