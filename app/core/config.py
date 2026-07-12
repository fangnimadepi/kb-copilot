from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "kb-copilot"

    # LLM
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    llm_model: str = "deepseek-chat"
    llm_timeout: float = 60.0  # 单次调用超时（秒）
    llm_max_retries: int = 3  # 首块响应前的最大重试次数
    llm_retry_base_delay: float = 0.5  # 指数退避基数：0.5s → 1s → 2s

    # 上下文窗口（token 预算，含历史消息；DeepSeek 上下文 64k，留足回答与余量）
    context_token_budget: int = 8000

    # 文档入库
    upload_dir: str = "data/uploads"

    # Embedding / Rerank
    embedding_api_key: str = ""
    embedding_base_url: str = "https://api.siliconflow.cn/v1"
    embedding_model: str = "BAAI/bge-m3"
    rerank_model: str = "BAAI/bge-reranker-v2-m3"

    # MySQL
    mysql_host: str = "127.0.0.1"
    mysql_port: int = 3306
    mysql_user: str = "kbcopilot"
    mysql_password: str = ""
    mysql_database: str = "kb_copilot"

    # Redis / Milvus
    redis_url: str = "redis://127.0.0.1:6379/0"
    milvus_uri: str = "http://127.0.0.1:19530"

    @property
    def mysql_dsn(self) -> str:
        return (
            f"mysql+aiomysql://{self.mysql_user}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}?charset=utf8mb4"
        )


settings = Settings()
