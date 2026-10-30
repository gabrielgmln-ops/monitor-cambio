# monitor-cambio/app/coleta.py
"""Coleta: busca na PTAX, grava o histórico e avalia os alertas."""
import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app import alertas, repositorio
from app.ptax import ClientePTAX, ErroPTAX

log = logging.getLogger(__name__)
FUSO = ZoneInfo("America/Sao_Paulo")


def hoje() -> date:
    # A PTAX é publicada no horário de Brasília; o container roda em UTC
    return datetime.now(FUSO).date()


def coletar(
    sessao: Session,
    cliente: ClientePTAX,
    moedas: list[str],
    inicio: date | None = None,
    fim: date | None = None,
) -> dict[str, dict]:
    """Coleta o período [inicio, fim] (padrão: últimos 10 dias, o que inclui o último dia útil).

    Uma moeda com falha não impede as outras; o erro volta no resumo.
    """
    fim = fim or hoje()
    inicio = inicio or fim - timedelta(days=10)
    resumo: dict[str, dict] = {}
    for moeda in moedas:
        try:
            cotacoes = cliente.fechamentos(moeda, inicio, fim)
            novas = repositorio.salvar(sessao, cotacoes)
            disparos = alertas.processar(sessao, moeda)
            ultima = repositorio.ultima(sessao, moeda)
            resumo[moeda] = {
                "recebidas": len(cotacoes),
                "novas": novas,
                "ultima_data": ultima.data.isoformat() if ultima else None,
                "alertas": len(disparos),
            }
            log.info("Coleta %s: %s", moeda, resumo[moeda])
        except ErroPTAX as exc:
            log.error("Coleta %s falhou: %s", moeda, exc)
            resumo[moeda] = {"erro": str(exc)}
    return resumo
