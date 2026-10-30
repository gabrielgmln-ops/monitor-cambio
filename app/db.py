# monitor-cambio/app/db.py
"""Conexão com o banco via SQLAlchemy 2."""
from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import get_settings


class Base(DeclarativeBase):
    pass


@lru_cache
def get_engine() -> Engine:
    url = get_settings().database_url
    if url.startswith("sqlite"):
        # Testes: SQLite em memória precisa de UMA conexão compartilhada
        return create_engine(url, poolclass=StaticPool, connect_args={"check_same_thread": False})
    # pool_pre_ping descarta conexões mortas (ex.: banco reiniciado)
    return create_engine(url, pool_pre_ping=True)


@lru_cache
def _fabrica() -> sessionmaker[Session]:
    return sessionmaker(get_engine(), expire_on_commit=False)


def nova_sessao() -> Session:
    return _fabrica()()


def get_sessao() -> Iterator[Session]:
    """Dependência do FastAPI: uma sessão por requisição."""
    with nova_sessao() as s:
        yield s


def criar_tabelas() -> None:
    import app.models  # noqa: F401  (registra os modelos no metadata)

    Base.metadata.create_all(get_engine())


def banco_ok() -> bool:
    """True se o banco responde a um SELECT 1."""
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
