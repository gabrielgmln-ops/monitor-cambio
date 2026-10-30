# monitor-cambio/tests/test_api.py
"""Etapas 4 e 5: endpoints de consulta, regras e alertas, ponta a ponta com PTAX falsa."""
from unittest.mock import patch

import app.main as main


def coletar(api):
    resp = api.post("/coleta", params={"inicio": "2026-10-20", "fim": "2026-10-31"})
    assert resp.status_code == 200
    return resp.json()


def test_health(api):
    assert api.get("/health").json() == {"status": "ok", "banco": "ok", "moedas": ["USD", "EUR"]}


def test_health_banco_fora(api):
    with patch.object(main, "banco_ok", lambda: False):
        resp = api.get("/health")
    assert resp.status_code == 503 and resp.json()["banco"] == "indisponivel"


def test_coleta_resumo(api):
    resumo = coletar(api)
    assert resumo["USD"] == {"recebidas": 3, "novas": 3, "ultima_data": "2026-10-28", "alertas": 0}
    assert coletar(api)["USD"]["novas"] == 0


def test_atual_em_dia_sem_cotacao(api):
    coletar(api)
    corpo = api.get("/cotacoes/usd/atual", params={"data": "2026-10-31"}).json()
    assert corpo["data"] == "2026-10-28"
    assert corpo["venda"] == "5.390600"  # Decimal como string, sem float
    assert corpo["dia_util_anterior"] is True


def test_atual_sem_dados_e_moeda_invalida(api):
    assert api.get("/cotacoes/USD/atual").status_code == 404
    assert api.get("/cotacoes/JPY/atual").status_code == 404


def test_historico(api):
    coletar(api)
    corpo = api.get("/cotacoes/USD/historico", params={"inicio": "2026-10-27", "fim": "2026-10-31"}).json()
    assert [c["data"] for c in corpo] == ["2026-10-27", "2026-10-28"]
    assert api.get("/cotacoes/USD/historico", params={"inicio": "2026-11-01", "fim": "2026-10-01"}).status_code == 422


def test_variacao_ancora_no_dia_anterior(api):
    coletar(api)
    corpo = api.get("/cotacoes/USD/variacao", params={"inicio": "2026-10-27", "fim": "2026-10-31"}).json()
    # 26/10 fica fora do período mas serve de base: 27/10 já tem variação diária
    assert corpo["serie"][0]["variacao_diaria_pct"] == "0.9229"   # 5.5006 / 5.4503
    assert corpo["serie"][1]["variacao_diaria_pct"] == "-1.9998"  # 5.3906 / 5.5006
    assert corpo["variacao_acumulada_pct"] == "-1.0954"  # 5.3906 / 5.4503: desde o fechamento anterior ao período


def test_regra_acima_dispara_uma_vez(api, caplog):
    r = api.post("/regras", json={"moeda": "usd", "tipo": "abaixo", "valor": "5.40"})
    assert r.status_code == 201 and r.json()["moeda"] == "USD"
    resumo = coletar(api)
    assert resumo["USD"]["alertas"] == 1
    assert "abaixo de 5.400000" in caplog.text
    assert coletar(api)["USD"]["alertas"] == 0  # mesmo dia de cotação: não repete
    [alerta] = api.get("/alertas").json()
    assert alerta["data_cotacao"] == "2026-10-28"


def test_regra_variacao_diaria(api):
    api.post("/regras", json={"moeda": "USD", "tipo": "variacao_diaria", "valor": "1.5"})
    api.post("/regras", json={"moeda": "USD", "tipo": "variacao_diaria", "valor": "3"})
    assert coletar(api)["USD"]["alertas"] == 1  # queda de 1,9998%: só a regra de 1,5% dispara


def test_regra_invalida_e_desativar(api):
    assert api.post("/regras", json={"moeda": "USD", "tipo": "x", "valor": "1"}).status_code == 422
    assert api.post("/regras", json={"moeda": "USD", "tipo": "acima", "valor": "-1"}).status_code == 422
    rid = api.post("/regras", json={"moeda": "USD", "tipo": "acima", "valor": "1"}).json()["id"]
    assert api.delete(f"/regras/{rid}").status_code == 204
    assert api.get("/regras").json()[0]["ativa"] is False
    assert coletar(api)["USD"]["alertas"] == 0
    assert api.delete("/regras/999").status_code == 404


def test_email_enviado_quando_configurado(api, monkeypatch):
    from app import alertas
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "smtp_host", "smtp.teste")
    enviados = []
    monkeypatch.setattr(alertas, "_enviar_email", lambda d, m: enviados.append((d, m)))
    api.post("/regras", json={"moeda": "EUR", "tipo": "acima", "valor": "6", "email": "eu@exemplo.com"})
    coletar(api)
    assert enviados and enviados[0][0] == "eu@exemplo.com"


def test_coleta_so_inicio_respeita_limite(api):
    assert api.post("/coleta", params={"inicio": "1990-01-01"}).status_code == 422
    assert api.post("/coleta", params={"inicio": "2026-10-31", "fim": "2026-10-01"}).status_code == 422


def test_email_invalido_rejeitado(api):
    corpo = {"moeda": "USD", "tipo": "acima", "valor": "1", "email": "a@x.com, b@y.com"}
    assert api.post("/regras", json=corpo).status_code == 422


def test_token_exigido_quando_configurado(api, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "api_token", "segredo-teste")
    assert api.get("/regras").status_code == 401
    assert api.get("/regras", headers={"X-API-Token": "errado"}).status_code == 401
    assert api.get("/regras", headers={"X-API-Token": "segredo-teste"}).status_code == 200
    assert api.get("/health").status_code == 200  # consulta pública continua aberta
