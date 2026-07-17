# Deploy do bot na máquina de IA (.90)

O `bot/` roda na **.90** (máquina do ollama), extraindo o mapa das fontes pendentes
**via rolhama** (concentrador webapi → ollama de slot único; não colide com os outros
consumidores — enfileira o pedido por canal e acompanha o job pelo UUID). NÃO vai pra
Hostinger (lá só a `api/`).

## Passos (na .90)
```bash
# 1. código
mkdir -p ~/kdd_bot && (cd bot && tar czf - --exclude=.venv --exclude=__pycache__ .) | ssh <90> 'tar xzf - -C ~/kdd_bot'
# 2. deps (venv próprio ou reaproveitar um): requests + pypdf
python -m venv ~/kdd_bot/.venv && ~/kdd_bot/.venv/bin/pip install requests pypdf
# 3. .env (chmod 600) — KDD + rolhama:
#    KDD_APP_URL, KDD_TOKEN_OPERADOR, KDD_IA_BACKEND=rolhama,
#    ROLHAMA_WEBAPI_URL (default https://wellington.tec.br/rolhama), ROLHAMA_BDD_KEY,
#    ROLHAMA_CHANNEL=505, ROLHAMA_OLLAMA_MODEL=qwen2.5:14b-instruct
# 4. serviço
sudo cp deploy/kdd_bot.service /etc/systemd/system/ && sudo systemctl enable --now kdd_bot.service
```
Ajuste `ExecStart`/`EnvironmentFile` no unit se o caminho do venv/dir mudar.
Canal 505 = o reservado ao KDD no rolhama (o worker atende 500, 502–505; hacker usa 502/503/504).
