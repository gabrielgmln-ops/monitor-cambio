# monitor-cambio/tests/conftest.py
"""Fixtures comuns. Sem DATABASE_URL no ambiente, usa SQLite em memória;
no CI, a variável aponta para um PostgreSQL de verdade."""
import json
import os
from datetime import date

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("MOEDAS", "usd, eur")
os.environ["API_TOKEN"] = "token-teste"
os.environ["AGENDADOR_ATIVO"] = "false"  # nada de coleta real durante os testes
os.environ.pop("SMTP_HOST", None)

import httpx  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app.models  # noqa: E402,F401
from app.db import Base, get_engine, nova_sessao  # noqa: E402
from app.ptax import ClientePTAX  # noqa: E402


@pytest.fixture(autouse=True)
def banco_limpo():
    """Tabelas recriadas a cada teste: nenhum teste depende de outro."""
    Base.metadata.drop_all(get_engine())
    Base.metadata.create_all(get_engine())
    yield


@pytest.fixture
def sessao():
    with nova_sessao() as s:
        yield s


def boletim(dia: str, compra: str, venda: str, tipo: str = "Fechamento") -> dict:
    """Item no formato real da API Olinda (valores como número JSON)."""
    return {
        "paridadeCompra": 1.0, "paridadeVenda": 1.0,
        "cotacaoCompra": compra, "cotacaoVenda": venda,  # viram números no json.dumps abaixo
        "dataHoraCotacao": f"{dia} 13:09:51.019788", "tipoBoletim": tipo,
    }


def resposta_olinda(itens: list[dict]) -> str:
    # Escreve os valores como números literais (sem aspas), como a API real
    texto = json.dumps({"value": itens})
    for item in itens:
        for chave in ("cotacaoCompra", "cotacaoVenda"):
            texto = texto.replace(f'"{chave}": "{item[chave]}"', f'"{chave}": {item[chave]}')
    return texto


@pytest.fixture
def fake_ptax():
    """Fábrica de ClientePTAX com respostas fixas por moeda e registro das requisições."""

    def fabricar(por_moeda: dict[str, list[dict]], status: int = 200):
        chamadas: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response:
            chamadas.append(req)
            moeda = req.url.params["@moeda"].strip("'")
            return httpx.Response(status, text=resposta_olinda(por_moeda.get(moeda, [])))

        cliente = ClientePTAX(httpx.Client(transport=httpx.MockTransport(handler)))
        cliente.chamadas = chamadas
        return cliente

    return fabricar


@pytest.fixture
def api(fake_ptax):
    """TestClient com a PTAX falsa já injetada."""
    from app.main import app, get_cliente

    dados = {
        "USD": [
            boletim("2026-10-26", "5.4497", "5.4503", "Abertura"),
            boletim("2026-10-26", "5.4497", "5.4503"),
            boletim("2026-10-27", "5.5000", "5.5006"),
            boletim("2026-10-28", "5.3900", "5.3906"),
        ],
        "EUR": [boletim("2026-10-28", "6.3000", "6.3010")],
    }
    app.dependency_overrides[get_cliente] = lambda: fake_ptax(dados)
    with TestClient(app, headers={"X-API-Token": "token-teste"}) as c:
        yield c
    app.dependency_overrides.clear()


HOJE_FIXO = date(2026, 10, 31)  # sábado: sem PTAX
