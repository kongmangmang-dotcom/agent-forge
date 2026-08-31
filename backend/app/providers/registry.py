"""Provider 注册表 — 按 kind 解析 Adapter 实现。"""

from app.domain.provider import AgentProvider, ProviderConfig
from app.models.provider import ProviderModel
from app.providers.cli_coding import (
    CodexCliProvider,
    CursorCliProvider,
    DemoCliProvider,
    OpencodeCliProvider,
)


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, object] = {}

    def register(self, kind: str, provider: object) -> None:
        self._providers[kind] = provider

    def get(self, kind: str) -> object | None:
        return self._providers.get(kind)

    def kinds(self) -> list[str]:
        return list(self._providers.keys())

    @staticmethod
    def provider_config_from_model(row: ProviderModel) -> ProviderConfig:
        return ProviderConfig(
            id=row.id,
            kind=row.kind,
            type=row.type,
            endpoint=row.endpoint,
            default_model=row.default_model,
            config=row.config_encrypted or {},
        )


registry = ProviderRegistry()

# Register CLI coding agents
_demo = DemoCliProvider()
_codex = CodexCliProvider()
_opencode = OpencodeCliProvider()
_cursor = CursorCliProvider()

for kind, impl in [
    ("demo_cli", _demo),
    ("codex_cli", _codex),
    ("opencode_cli", _opencode),
    ("cursor_cli", _cursor),
]:
    registry.register(kind, impl)

