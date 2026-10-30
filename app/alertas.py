# monitor-cambio/app/alertas.py
"""Avaliação das regras de alerta e disparo (log sempre; e-mail se configurado)."""
import logging
import smtplib
from decimal import Decimal
from email.message import EmailMessage

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import repositorio
from app.config import get_settings
from app.models import AlertaDisparado, CotacaoDB, RegraAlerta
from app.variacao import pct

log = logging.getLogger("monitor_cambio.alertas")

TIPOS = ("acima", "abaixo", "variacao_diaria")


def avaliar(regra: RegraAlerta, atual: CotacaoDB, anterior: CotacaoDB | None) -> str | None:
    """Mensagem do alerta se a regra foi atingida pela cotação `atual`; senão None."""
    venda = atual.venda
    if regra.tipo == "acima" and venda > regra.valor:
        return f"{regra.moeda} PTAX venda {venda} acima de {regra.valor} em {atual.data}"
    if regra.tipo == "abaixo" and venda < regra.valor:
        return f"{regra.moeda} PTAX venda {venda} abaixo de {regra.valor} em {atual.data}"
    if regra.tipo == "variacao_diaria" and anterior is not None:
        var = pct(venda, anterior.venda)
        # Regra vale para alta ou queda: compara o módulo
        if abs(var) > regra.valor:
            return (
                f"{regra.moeda} variou {var}% em {atual.data} "
                f"({anterior.venda} -> {venda}), limite {regra.valor}%"
            )
    return None


def _enviar_email(destino: str, mensagem: str) -> None:
    cfg = get_settings()
    msg = EmailMessage()
    msg["Subject"] = "[Monitor de Câmbio] Alerta"
    msg["From"] = cfg.smtp_remetente
    msg["To"] = destino
    msg.set_content(mensagem)
    with smtplib.SMTP(cfg.smtp_host or "", cfg.smtp_port, timeout=15) as smtp:
        smtp.starttls()
        if cfg.smtp_usuario:
            smtp.login(cfg.smtp_usuario, cfg.smtp_senha or "")
        smtp.send_message(msg)


def disparar(regra: RegraAlerta, mensagem: str) -> None:
    log.warning("ALERTA regra=%s: %s", regra.id, mensagem)
    if regra.email and get_settings().smtp_host:
        try:
            _enviar_email(regra.email, mensagem)
        except (OSError, smtplib.SMTPException) as exc:
            # Falha de e-mail não pode derrubar a coleta; o alerta já está no log e no banco
            log.error("Falha ao enviar e-mail da regra %s: %s", regra.id, exc)


def processar(sessao: Session, moeda: str) -> list[AlertaDisparado]:
    """Avalia as regras ativas de `moeda` contra a última cotação. Retorna os disparos novos."""
    atual = repositorio.ultima(sessao, moeda)
    if atual is None:
        return []
    anterior = repositorio.anterior(sessao, moeda, atual.data)
    regras = sessao.scalars(
        select(RegraAlerta).where(RegraAlerta.moeda == moeda.upper(), RegraAlerta.ativa.is_(True))
    )
    novos = []
    for regra in regras:
        mensagem = avaliar(regra, atual, anterior)
        if mensagem is None:
            continue
        ja = sessao.scalar(
            select(AlertaDisparado).where(
                AlertaDisparado.regra_id == regra.id, AlertaDisparado.data_cotacao == atual.data
            )
        )
        if ja:
            continue  # já avisado para este dia de cotação
        alerta = AlertaDisparado(regra_id=regra.id, data_cotacao=atual.data, mensagem=mensagem)
        sessao.add(alerta)
        sessao.commit()
        disparar(regra, mensagem)
        novos.append(alerta)
    return novos


def validar_regra(tipo: str, valor: Decimal) -> None:
    if tipo not in TIPOS:
        raise ValueError(f"tipo deve ser um de {TIPOS}")
    if valor <= 0:
        raise ValueError("valor deve ser positivo")
