# Monitor de Câmbio

Serviço que coleta a cotação **PTAX** oficial do Banco Central (API pública Olinda),
guarda o histórico em PostgreSQL, calcula variação diária e acumulada e dispara
alertas (log e e-mail) quando regras cadastradas são atingidas.

- Valores monetários sempre em `Decimal` (o JSON da API é lido com `parse_float=Decimal`)
- Dia sem cotação (fim de semana, feriado) → último dia útil anterior
- Coleta automática em dias úteis, 13:30 e 18:00 (horário de Brasília)
- Fora do escopo: cotação de mercado em tempo real, corretagem

## Subir

```bash
cp .env.example .env          # troque a senha
docker compose up -d --build
curl http://localhost:8010/health
curl -X POST -H "X-API-Token: $API_TOKEN" "http://localhost:8010/coleta?inicio=2026-10-01&fim=2026-10-31"   # carga inicial
```

Portas no host: API `8010`, Postgres `5435` (ajustáveis com `API_PORTA_HOST` e `DB_PORTA_HOST`).
Documentação interativa: http://localhost:8010/docs

## Endpoints

| Método | Rota | O que faz |
|---|---|---|
| GET | `/health` | Estado do serviço e do banco |
| GET | `/cotacoes/{moeda}/atual?data=` | PTAX da data (ou do último dia útil) |
| GET | `/cotacoes/{moeda}/historico?inicio=&fim=` | Série histórica (padrão: 30 dias) |
| GET | `/cotacoes/{moeda}/variacao?inicio=&fim=` | Variação diária e acumulada |
| POST | `/coleta?inicio=&fim=` | Coleta manual |
| POST/GET | `/regras` | Cadastra / lista regras de alerta |
| DELETE | `/regras/{id}` | Desativa a regra |
| GET | `/alertas` | Alertas disparados |

Regras: `{"moeda":"USD","tipo":"acima","valor":"5.60","email":"opcional@x.com"}`.
Tipos: `acima`, `abaixo` (preço de venda em R$) e `variacao_diaria` (% em módulo).
Cada regra dispara no máximo uma vez por dia de cotação.

Coleta, regras e alertas exigem o cabeçalho `X-API-Token` com o valor de `API_TOKEN` do `.env`;
sem `API_TOKEN` configurado essas rotas respondem 503 (falha fechada). Cotações e `/health` são públicos.

## Testes

```bash
python -m venv .venv && . .venv/Scripts/activate
pip install -r requirements.txt
pytest -q
```

Localmente rodam em SQLite em memória; no CI (GitHub Actions), em PostgreSQL 16.
