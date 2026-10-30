# monitor-cambio/app/ptax.py
"""Cliente da API pública PTAX do Banco Central (Olinda).

Documentação: https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/aplicacao
A API devolve vários boletins por dia (Abertura, Intermediário, Fechamento);
a PTAX oficial do dia é o boletim de "Fechamento".
"""
import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

import httpx

log = logging.getLogger(__name__)

URL_BASE = "https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata"
# Janela de busca para trás: cobre fim de semana + feriados emendados (ex.: Carnaval)
DIAS_RETROCESSO = 10


class ErroPTAX(Exception):
    """Falha de comunicação ou resposta inesperada da API do BC."""


class SemCotacao(ErroPTAX):
    """Nenhum boletim de fechamento na janela consultada."""


@dataclass(frozen=True)
class Cotacao:
    moeda: str
    data: date            # dia útil a que a cotação se refere
    compra: Decimal
    venda: Decimal


def _fmt(d: date) -> str:
    # A API Olinda exige datas no formato americano MM-DD-AAAA
    return d.strftime("%m-%d-%Y")


class ClientePTAX:
    def __init__(self, client: httpx.Client | None = None, timeout: float = 15.0):
        # O client injetável permite testes com httpx.MockTransport
        self._client = client or httpx.Client(timeout=timeout)

    def fechamentos(self, moeda: str, inicio: date, fim: date) -> list[Cotacao]:
        """Todos os fechamentos PTAX de `moeda` entre `inicio` e `fim` (inclusive)."""
        url = (
            f"{URL_BASE}/CotacaoMoedaPeriodo(moeda=@moeda,dataInicial=@dataInicial,"
            "dataFinalCotacao=@dataFinalCotacao)"
        )
        params = {
            "@moeda": f"'{moeda.upper()}'",
            "@dataInicial": f"'{_fmt(inicio)}'",
            "@dataFinalCotacao": f"'{_fmt(fim)}'",
            "$format": "json",
        }
        try:
            resp = self._client.get(url, params=params)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise ErroPTAX(f"falha ao consultar PTAX {moeda}: {exc}") from exc

        try:
            # parse_float=Decimal: o valor nunca passa por float (5.4503 continua 5.4503)
            corpo = json.loads(resp.text, parse_float=Decimal)
            itens = corpo["value"]
        except (ValueError, KeyError) as exc:
            raise ErroPTAX(f"resposta inválida da PTAX: {exc}") from exc

        resultado = []
        for item in itens:
            if item.get("tipoBoletim") != "Fechamento":
                continue
            dia = datetime.fromisoformat(item["dataHoraCotacao"]).date()
            resultado.append(
                Cotacao(moeda.upper(), dia, Decimal(item["cotacaoCompra"]), Decimal(item["cotacaoVenda"]))
            )
        return sorted(resultado, key=lambda c: c.data)

    def cotacao_em(self, moeda: str, dia: date) -> Cotacao:
        """PTAX de `dia`; se não houver (fim de semana/feriado), a do último dia útil anterior."""
        lista = self.fechamentos(moeda, dia - timedelta(days=DIAS_RETROCESSO), dia)
        if not lista:
            raise SemCotacao(f"sem PTAX de {moeda} nos {DIAS_RETROCESSO} dias até {dia}")
        ultima = lista[-1]
        if ultima.data != dia:
            log.info("Sem PTAX %s em %s; usando último dia útil %s", moeda, dia, ultima.data)
        return ultima
