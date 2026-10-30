# monitor-cambio/tests/test_repositorio_variacao.py
"""Etapas 2 e 3: persistência idempotente e cálculo de variação."""
from datetime import date
from decimal import Decimal

from app import repositorio
from app.ptax import Cotacao
from app.variacao import serie_variacao

D = Decimal


def test_salvar_e_idempotente(sessao):
    c = Cotacao("USD", date(2026, 10, 26), D("5.4497"), D("5.4503"))
    assert repositorio.salvar(sessao, [c]) == 1
    assert repositorio.salvar(sessao, [c]) == 0  # recoleta não duplica
    assert len(repositorio.historico(sessao, "USD", date(2026, 10, 1), date(2026, 10, 31))) == 1


def test_ultima_ate_feriado_pega_dia_util_anterior(sessao):
    repositorio.salvar(sessao, [
        Cotacao("USD", date(2026, 10, 30), D("5.40"), D("5.41")),
        Cotacao("USD", date(2026, 11, 3), D("5.50"), D("5.51")),
    ])
    # 02/11 (Finados) sem PTAX: vale a de 30/10
    c = repositorio.ultima(sessao, "USD", ate=date(2026, 11, 2))
    assert c.data == date(2026, 10, 30) and c.venda == D("5.41")


def test_variacao_diaria_e_acumulada():
    serie = serie_variacao([
        (date(2026, 10, 27), D("5.5000")),
        (date(2026, 10, 26), D("5.0000")),  # fora de ordem de propósito
        (date(2026, 10, 28), D("5.2250")),
    ])
    assert [p.data.day for p in serie] == [26, 27, 28]
    assert serie[0].variacao_diaria_pct is None
    assert serie[1].variacao_diaria_pct == D("10.0000")
    assert serie[2].variacao_diaria_pct == D("-5.0000")
    assert serie[2].variacao_acumulada_pct == D("4.5000")


def test_variacao_arredondamento_bancario():
    # 1/3 de alta: 33.33333...% -> 33.3333
    serie = serie_variacao([(date(2026, 1, 1), D("3")), (date(2026, 1, 2), D("4"))])
    assert serie[1].variacao_diaria_pct == D("33.3333")


def test_variacao_vazia():
    assert serie_variacao([]) == []
