# monitor-cambio/app/main.py
"""API do Monitor de Câmbio."""
import logging
from contextlib import asynccontextmanager
from datetime import date, timedelta
from decimal import Decimal
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import JSONResponse
import secrets

from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import alertas, repositorio
from app.coleta import coletar, hoje
from app.config import get_settings
from app.db import banco_ok, criar_tabelas, get_sessao
from app.models import AlertaDisparado, RegraAlerta
from app.ptax import ClientePTAX
from app.variacao import serie_variacao

logging.basicConfig(level=get_settings().log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    criar_tabelas()
    agendador = None
    if get_settings().agendador_ativo:
        from app.agendador import criar_agendador

        agendador = criar_agendador()
        agendador.start()
    yield
    if agendador:
        agendador.shutdown(wait=False)


app = FastAPI(title="Monitor de Câmbio", version="1.0.0", lifespan=lifespan)
Sessao = Annotated[Session, Depends(get_sessao)]


def exigir_token(x_api_token: Annotated[str | None, Header()] = None) -> None:
    """Protege regras, alertas e coleta manual com o token de API_TOKEN.

    Sem API_TOKEN configurado, só aceita em modo aberto (desenvolvimento local).
    """
    esperado = get_settings().api_token
    if esperado and not (x_api_token and secrets.compare_digest(x_api_token, esperado)):
        raise HTTPException(401, "token inválido ou ausente (cabeçalho X-API-Token)")


Protegido = [Depends(exigir_token)]


def get_cliente() -> ClientePTAX:
    return ClientePTAX()


# ---------- Schemas (Decimal serializado como string para não perder precisão) ----------

class CotacaoOut(BaseModel):
    moeda: str
    data: date
    compra: Decimal
    venda: Decimal


class AtualOut(CotacaoOut):
    data_consultada: date
    dia_util_anterior: bool  # True quando a data pedida não teve PTAX


class PontoOut(BaseModel):
    data: date
    venda: Decimal
    variacao_diaria_pct: Decimal | None
    variacao_acumulada_pct: Decimal


class VariacaoOut(BaseModel):
    moeda: str
    inicio: date
    fim: date
    variacao_acumulada_pct: Decimal | None
    serie: list[PontoOut]


class RegraIn(BaseModel):
    moeda: str = Field(min_length=3, max_length=3)
    tipo: str = Field(description="acima | abaixo | variacao_diaria")
    valor: Decimal = Field(gt=0, max_digits=18, decimal_places=6)
    email: EmailStr | None = None  # rejeita listas de destinatários e quebras de linha


class RegraOut(RegraIn):
    id: int
    ativa: bool


class AlertaOut(BaseModel):
    id: int
    regra_id: int
    data_cotacao: date
    mensagem: str


def _moeda_valida(moeda: str) -> str:
    moeda = moeda.upper()
    if moeda not in get_settings().lista_moedas:
        raise HTTPException(404, f"moeda {moeda} não monitorada")
    return moeda


# ---------- Endpoints ----------

@app.get("/health")
def health() -> JSONResponse:
    """200 se o banco responde; 503 caso contrário (útil para o Compose)."""
    ok = banco_ok()
    corpo = {
        "status": "ok" if ok else "degradado",
        "banco": "ok" if ok else "indisponivel",
        "moedas": get_settings().lista_moedas,
    }
    return JSONResponse(corpo, status_code=200 if ok else 503)


@app.get("/cotacoes/{moeda}/atual", response_model=AtualOut)
def cotacao_atual(moeda: str, sessao: Sessao, data: date | None = None):
    """PTAX da data (padrão: hoje). Sem cotação no dia, devolve o último dia útil."""
    moeda = _moeda_valida(moeda)
    alvo = data or hoje()
    c = repositorio.ultima(sessao, moeda, ate=alvo)
    if c is None:
        raise HTTPException(404, f"sem cotação de {moeda} até {alvo}; rode POST /coleta")
    return AtualOut(
        moeda=c.moeda, data=c.data, compra=c.compra, venda=c.venda,
        data_consultada=alvo, dia_util_anterior=c.data != alvo,
    )


@app.get("/cotacoes/{moeda}/historico", response_model=list[CotacaoOut])
def historico(moeda: str, sessao: Sessao, inicio: date | None = None, fim: date | None = None):
    moeda = _moeda_valida(moeda)
    fim = fim or hoje()
    inicio = inicio or fim - timedelta(days=30)
    if inicio > fim:
        raise HTTPException(422, "inicio deve ser <= fim")
    return [CotacaoOut(moeda=c.moeda, data=c.data, compra=c.compra, venda=c.venda)
            for c in repositorio.historico(sessao, moeda, inicio, fim)]


@app.get("/cotacoes/{moeda}/variacao", response_model=VariacaoOut)
def variacao(moeda: str, sessao: Sessao, inicio: date | None = None, fim: date | None = None):
    """Variação diária de cada dia útil e acumulada no período (sobre a PTAX de venda)."""
    moeda = _moeda_valida(moeda)
    fim = fim or hoje()
    inicio = inicio or fim - timedelta(days=30)
    if inicio > fim:
        raise HTTPException(422, "inicio deve ser <= fim")
    pontos = [(c.data, c.venda) for c in repositorio.historico(sessao, moeda, inicio, fim)]
    # Ancora no último dia útil ANTES do período, para o primeiro dia também ter variação diária
    base = repositorio.anterior(sessao, moeda, inicio)
    if base:
        pontos.insert(0, (base.data, base.venda))
    serie = serie_variacao(pontos)
    if base:
        serie = serie[1:]
    return VariacaoOut(
        moeda=moeda, inicio=inicio, fim=fim,
        variacao_acumulada_pct=serie[-1].variacao_acumulada_pct if serie else None,
        serie=[PontoOut(**p.__dict__) for p in serie],
    )


@app.post("/coleta", dependencies=Protegido)
def coleta_manual(
    sessao: Sessao,
    cliente: Annotated[ClientePTAX, Depends(get_cliente)],
    inicio: date | None = None,
    fim: date | None = None,
):
    """Dispara a coleta agora (útil para carga inicial do histórico)."""
    # Resolve os padrões ANTES de validar: só `inicio` não pode virar "desde 1990 até hoje"
    fim = fim or hoje()
    inicio = inicio or fim - timedelta(days=10)
    if inicio > fim:
        raise HTTPException(422, "inicio deve ser <= fim")
    if (fim - inicio).days > 366:
        raise HTTPException(422, "período máximo de 366 dias por coleta")
    return coletar(sessao, cliente, get_settings().lista_moedas, inicio, fim)


@app.post("/regras", response_model=RegraOut, status_code=201, dependencies=Protegido)
def criar_regra(regra: RegraIn, sessao: Sessao):
    moeda = _moeda_valida(regra.moeda)
    try:
        alertas.validar_regra(regra.tipo, regra.valor)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    nova = RegraAlerta(moeda=moeda, tipo=regra.tipo, valor=regra.valor, email=regra.email, ativa=True)
    sessao.add(nova)
    sessao.commit()
    return RegraOut(id=nova.id, moeda=nova.moeda, tipo=nova.tipo, valor=nova.valor,
                    email=nova.email, ativa=nova.ativa)


@app.get("/regras", response_model=list[RegraOut], dependencies=Protegido)
def listar_regras(sessao: Sessao):
    return [RegraOut(id=r.id, moeda=r.moeda, tipo=r.tipo, valor=r.valor, email=r.email, ativa=r.ativa)
            for r in sessao.scalars(select(RegraAlerta).order_by(RegraAlerta.id))]


@app.delete("/regras/{regra_id}", status_code=204, dependencies=Protegido)
def desativar_regra(regra_id: int, sessao: Sessao):
    """Desativa (não apaga): o histórico de alertas continua apontando para a regra."""
    regra = sessao.get(RegraAlerta, regra_id)
    if regra is None:
        raise HTTPException(404, "regra não encontrada")
    regra.ativa = False
    sessao.commit()


@app.get("/alertas", response_model=list[AlertaOut], dependencies=Protegido)
def listar_alertas(sessao: Sessao, limite: Annotated[int, Query(ge=1, le=500)] = 50):
    q = select(AlertaDisparado).order_by(AlertaDisparado.id.desc()).limit(limite)
    return [AlertaOut(id=a.id, regra_id=a.regra_id, data_cotacao=a.data_cotacao, mensagem=a.mensagem)
            for a in sessao.scalars(q)]
