# monitor-cambio/app/models.py
"""Tabelas: histórico de cotações, regras de alerta e alertas disparados."""
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

# 18 dígitos, 6 decimais: a PTAX publica 4 casas; folga para percentuais
VALOR = Numeric(18, 6, asdecimal=True)


def _agora() -> datetime:
    return datetime.now(timezone.utc)


class CotacaoDB(Base):
    __tablename__ = "cotacoes"
    __table_args__ = (UniqueConstraint("moeda", "data", name="uq_cotacao_moeda_data"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    moeda: Mapped[str] = mapped_column(String(3), index=True)
    data: Mapped[date] = mapped_column(Date, index=True)
    compra: Mapped[Decimal] = mapped_column(VALOR)
    venda: Mapped[Decimal] = mapped_column(VALOR)
    coletada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_agora)


class RegraAlerta(Base):
    __tablename__ = "regras_alerta"

    id: Mapped[int] = mapped_column(primary_key=True)
    moeda: Mapped[str] = mapped_column(String(3))
    # "acima" | "abaixo" (valor = preço em R$) ou "variacao_diaria" (valor = % absoluto)
    tipo: Mapped[str] = mapped_column(String(20))
    valor: Mapped[Decimal] = mapped_column(VALOR)
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    ativa: Mapped[bool] = mapped_column(Boolean, default=True)
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_agora)


class AlertaDisparado(Base):
    __tablename__ = "alertas_disparados"
    # Uma regra dispara no máximo uma vez por dia de cotação (evita repetir a cada coleta)
    __table_args__ = (UniqueConstraint("regra_id", "data_cotacao", name="uq_alerta_regra_dia"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    regra_id: Mapped[int] = mapped_column(ForeignKey("regras_alerta.id", ondelete="CASCADE"))
    data_cotacao: Mapped[date] = mapped_column(Date)
    mensagem: Mapped[str] = mapped_column(String(500))
    disparado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_agora)
