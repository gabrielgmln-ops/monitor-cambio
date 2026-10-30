# monitor-cambio/app/config.py
"""Configuração lida exclusivamente de variáveis de ambiente (ou .env)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Sem valor padrão de propósito: segredo ausente deve falhar cedo
    database_url: str
    # Moedas acompanhadas, separadas por vírgula (ex.: "USD,EUR")
    moedas: str = "USD,EUR"
    log_level: str = "INFO"
    # Token exigido (cabeçalho X-API-Token) em coleta, regras e alertas. Vazio = rotas protegidas recusadas (503).
    api_token: str | None = None

    # Agendador: horários (America/Sao_Paulo) da coleta em dias úteis.
    # A PTAX de fechamento sai por volta das 13h; 13:30 coleta, 18:00 confere de novo.
    agendador_ativo: bool = True
    horarios_coleta: str = "13:30,18:00"

    # E-mail de alertas: opcional. Sem SMTP_HOST, o alerta vai só para o log.
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_usuario: str | None = None
    smtp_senha: str | None = None
    smtp_remetente: str = "monitor-cambio@localhost"

    @property
    def lista_moedas(self) -> list[str]:
        """Converte "usd, eur" em ["USD", "EUR"], ignorando vazios."""
        return [m.strip().upper() for m in self.moedas.split(",") if m.strip()]


@lru_cache
def get_settings() -> Settings:
    """Instância única, criada na primeira chamada."""
    return Settings()
