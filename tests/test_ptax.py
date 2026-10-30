# monitor-cambio/tests/test_ptax.py
"""Etapa 1: cliente PTAX, parsing em Decimal e dia sem cotação."""
from datetime import date
from decimal import Decimal

import pytest

from app.ptax import ErroPTAX, SemCotacao
from tests.conftest import boletim


def test_so_fechamento_e_em_decimal(fake_ptax):
    cliente = fake_ptax({"USD": [
        boletim("2026-10-26", "5.6036", "5.6052", "Abertura"),
        boletim("2026-10-26", "5.4497", "5.4503", "Intermediário"),
        boletim("2026-10-26", "5.4497", "5.4503"),
    ]})
    [c] = cliente.fechamentos("usd", date(2026, 10, 26), date(2026, 10, 26))
    assert c.moeda == "USD" and c.data == date(2026, 10, 26)
    assert c.venda == Decimal("5.4503") and isinstance(c.venda, Decimal)


def test_parametros_no_formato_olinda(fake_ptax):
    cliente = fake_ptax({"USD": [boletim("2026-10-26", "5.4497", "5.4503")]})
    cliente.fechamentos("USD", date(2026, 10, 1), date(2026, 10, 26))
    params = cliente.chamadas[0].url.params
    assert params["@moeda"] == "'USD'"
    assert params["@dataInicial"] == "'10-01-2026'"      # MM-DD-AAAA
    assert params["@dataFinalCotacao"] == "'10-26-2026'"


def test_fim_de_semana_usa_ultimo_dia_util(fake_ptax):
    # Sábado 31/10: a última PTAX é a de sexta 30/10
    cliente = fake_ptax({"USD": [
        boletim("2026-10-29", "5.40", "5.41"),
        boletim("2026-10-30", "5.42", "5.43"),
    ]})
    c = cliente.cotacao_em("USD", date(2026, 10, 31))
    assert c.data == date(2026, 10, 30) and c.venda == Decimal("5.43")


def test_sem_cotacao_na_janela(fake_ptax):
    with pytest.raises(SemCotacao):
        fake_ptax({}).cotacao_em("USD", date(2026, 10, 31))


def test_erro_http_vira_erro_ptax(fake_ptax):
    with pytest.raises(ErroPTAX):
        fake_ptax({}, status=500).fechamentos("USD", date(2026, 10, 1), date(2026, 10, 2))
