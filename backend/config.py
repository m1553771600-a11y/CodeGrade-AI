# backend/config.py
# 项目唯一配置中心：从 .env.local 读取，全部字段给默认值以支持免配置启动（骨架期）。

import os
from functools import lru_cache
from pydantic_settings import BaseSettings

_live_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_env_local_path = os.path.join(_live_path, ".env.local")


class Settings(BaseSettings):
    class Config:
        env_file = _env_local_path
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"  # .env.local 里多出的字段忽略，不报错

    # ── 应用基础 ──
    app_env: str = "local"
    app_debug: bool = False
    app_host: str = "0.0.0.0"
    app_port: int = 8001
    log_level: str = "INFO"

    # ── 大模型（DeepSeek，OpenAI 兼容）──
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"

    # ── 评审参数 ──
    review_token_budget: int = 60000       # 单次评审送入 LLM 的总 token 预算
    review_upload_max_bytes: int = 209715200  # 200MB，只卡上传传输
    review_focus_file_limit: int = 15      # 焦点层文件数上限（受 token 预算动态裁量）
    review_giant_file_lines: int = 2000    # 单文件超过该行数 → 标「疑似巨石」

    # ── 数据库 / 认证（占位，M1 骨架不强依赖）──
    db_host: str = "localhost"
    db_port: int = 5433
    db_name: str = "code_eval"
    db_user: str = ""
    db_password: str = ""
    jwt_secret_key: str = "dev-secret"
    jwt_algorithm: str = "HS256"
    default_tenant_id: str = "tenant_default"

    # ── RAG / Milvus（M3 规范知识库）──
    milvus_host: str = "localhost"
    milvus_port: int = 19530
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    rag_collection: str = "code_style_docs"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )


@lru_cache()
def get_settings() -> Settings:
    return Settings()


config = Settings()