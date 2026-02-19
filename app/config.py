from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    api_id: int
    api_hash: str
    session_name: str = "data/smartsummary"

    openai_api_key: str = ""
    openai_model: str = "gpt-5.2"

    my_user_id: int = 33570147
    wife_chat_id: int = 578839877
    summary_hour: int = 23
    summary_minute: int = 0
    compliment_hour: int = 10
    compliment_minute: int = 0
    timezone: str = "Asia/Novosibirsk"

    # Bitrix24 OAuth
    bitrix_client_id: str = ""
    bitrix_client_secret: str = ""
    bitrix_domain: str = ""  # например "company.bitrix24.ru"
    bitrix_refresh_token: str = ""  # начальный refresh_token

    # Jira Server (Basic auth)
    jira_url: str = ""  # https://jira.dclouds.ru
    jira_username: str = ""
    jira_password: str = ""

    # группы для дневного отчёта (справочники)
    report_group_ids: list[int] = [-1001408128567]  # Digital Clouds

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
