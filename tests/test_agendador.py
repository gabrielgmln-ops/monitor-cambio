# monitor-cambio/tests/test_agendador.py
"""Etapa 6: agendamento em dias úteis no fuso de Brasília."""
from datetime import datetime

from app.agendador import criar_agendador
from app.coleta import FUSO


def test_jobs_em_dias_uteis():
    agendador = criar_agendador()
    jobs = {j.id: j for j in agendador.get_jobs()}
    assert set(jobs) == {"coleta-1330", "coleta-1800"}
    # Depois de sexta 30/10 às 19h, a próxima coleta é segunda 02/11 às 13:30
    sexta = datetime(2026, 10, 30, 19, 0, tzinfo=FUSO)
    proxima = jobs["coleta-1330"].trigger.get_next_fire_time(None, sexta)
    assert proxima == datetime(2026, 11, 2, 13, 30, tzinfo=FUSO)
