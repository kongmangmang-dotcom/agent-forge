from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://agentforge:agentforge@localhost:5434/agentforge"
    redis_url: str = "redis://localhost:6380/0"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: str = "http://localhost:5173,http://localhost:5174"

    # Knowledge RAG: OpenAI-compatible embeddings (optional; falls back to local_hash)
    embedding_api_url: str = ""
    embedding_api_key: str = ""
    embedding_model: str = "text-embedding-3-small"

    # Vector store: milvus | postgres (JSONB cosine). Default milvus for local/dev.
    vector_store: str = "milvus"
    milvus_host: str = "127.0.0.1"
    milvus_port: int = 19530
    milvus_collection: str = "agentforge_knowledge_segment"

    # Knowledge Q&A chat (optional; falls back to extractive answer from retrieved chunks)
    chat_api_url: str = ""
    chat_api_key: str = ""
    chat_model: str = "gpt-4o-mini"

    # Daily work report (22:00 Asia/Shanghai by default)
    app_tz: str = "Asia/Shanghai"
    daily_report_enabled: bool = True
    daily_report_hour: int = 22
    daily_report_minute: int = 0
    daily_report_kb_name: str = "工作总结"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
