# monitor-cambio/app/agendador.py
"""Coleta periódica com APScheduler, em dias úteis, no fuso de Brasília."""
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.coleta import FUSO, coletar
from app.config import get_settings
from app.db import nova_sessao
from app.ptax import ClientePTAX

log = logging.getLogger(__name__)


def tarefa_coleta() -> None:
    with nova_sessao() as sessao:
        coletar(sessao, ClientePTAX(), get_settings().lista_moedas)


def criar_agendador() -> BackgroundScheduler:
    agendador = BackgroundScheduler(timezone=FUSO)
    for horario in get_settings().horarios_coleta.split(","):
        hora, minuto = horario.strip().split(":")
        agendador.add_job(
            tarefa_coleta,
            CronTrigger(day_of_week="mon-fri", hour=int(hora), minute=int(minuto), timezone=FUSO),
            id=f"coleta-{hora}{minuto}",
            max_instances=1,      # nunca duas coletas simultâneas
            coalesce=True,        # se perdeu várias execuções, roda só uma
            misfire_grace_time=3600,
        )
    return agendador
