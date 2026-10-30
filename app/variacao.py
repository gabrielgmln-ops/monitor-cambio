# monitor-cambio/app/variacao.py
"""Variação diária e acumulada da PTAX de venda.

O pandas organiza a série (ordena, remove datas duplicadas, desloca o dia anterior);
a aritmética é feita em Decimal, nunca em float.
"""
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal

import pandas as pd

CEM = Decimal("100")
CASAS_PCT = Decimal("0.0001")  # percentuais com 4 casas


def pct(atual: Decimal, anterior: Decimal) -> Decimal:
    """Variação percentual com arredondamento bancário (meio para o par)."""
    return ((atual / anterior - 1) * CEM).quantize(CASAS_PCT, rounding=ROUND_HALF_EVEN)


@dataclass(frozen=True)
class PontoVariacao:
    data: date
    venda: Decimal
    variacao_diaria_pct: Decimal | None    # None no primeiro ponto (sem dia anterior)
    variacao_acumulada_pct: Decimal         # desde o primeiro ponto da série


def serie_variacao(pontos: list[tuple[date, Decimal]]) -> list[PontoVariacao]:
    """Recebe [(data, venda)] e devolve a série com variação diária e acumulada."""
    if not pontos:
        return []
    df = (
        pd.DataFrame(pontos, columns=["data", "venda"])
        .drop_duplicates(subset="data", keep="last")
        .sort_values("data")
        .reset_index(drop=True)
    )
    base = df.loc[0, "venda"]
    df["anterior"] = df["venda"].shift(1)  # no primeiro vira NaN; tratado abaixo

    resultado = []
    for linha in df.itertuples(index=False):
        anterior = linha.anterior if isinstance(linha.anterior, Decimal) else None
        resultado.append(
            PontoVariacao(
                data=linha.data,
                venda=linha.venda,
                variacao_diaria_pct=pct(linha.venda, anterior) if anterior else None,
                variacao_acumulada_pct=pct(linha.venda, base),
            )
        )
    return resultado
