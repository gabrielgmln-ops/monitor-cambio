# monitor-cambio/app/repositorio.py
"""Acesso ao histórico de cotações."""
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CotacaoDB
from app.ptax import Cotacao


def salvar(sessao: Session, cotacoes: list[Cotacao]) -> int:
    """Grava ou atualiza por (moeda, data). Idempotente: recoletar não duplica. Retorna novas."""
    novas = 0
    for c in cotacoes:
        existente = sessao.scalar(
            select(CotacaoDB).where(CotacaoDB.moeda == c.moeda, CotacaoDB.data == c.data)
        )
        if existente:
            existente.compra, existente.venda = c.compra, c.venda
        else:
            sessao.add(CotacaoDB(moeda=c.moeda, data=c.data, compra=c.compra, venda=c.venda))
            novas += 1
    sessao.commit()
    return novas


def ultima(sessao: Session, moeda: str, ate: date | None = None) -> CotacaoDB | None:
    """Cotação mais recente até `ate`; é o "último dia útil" quando `ate` não tem PTAX."""
    q = select(CotacaoDB).where(CotacaoDB.moeda == moeda.upper())
    if ate:
        q = q.where(CotacaoDB.data <= ate)
    return sessao.scalar(q.order_by(CotacaoDB.data.desc()).limit(1))


def anterior(sessao: Session, moeda: str, data: date) -> CotacaoDB | None:
    """Cotação do dia útil imediatamente anterior a `data`."""
    q = (
        select(CotacaoDB)
        .where(CotacaoDB.moeda == moeda.upper(), CotacaoDB.data < data)
        .order_by(CotacaoDB.data.desc())
        .limit(1)
    )
    return sessao.scalar(q)


def historico(sessao: Session, moeda: str, inicio: date, fim: date) -> list[CotacaoDB]:
    q = (
        select(CotacaoDB)
        .where(CotacaoDB.moeda == moeda.upper(), CotacaoDB.data >= inicio, CotacaoDB.data <= fim)
        .order_by(CotacaoDB.data)
    )
    return list(sessao.scalars(q))
