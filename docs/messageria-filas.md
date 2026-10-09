# Messageria e filas no KDD — como o processamento é disparado

> **Documento de análise.** Responde à pergunta do idealizador (2026-10-09): *"todo o
> processamento é feito em bots, confirma para mim se os bots têm messageria"*. Verificado no
> código, não na documentação. Última atualização: 2026-10-09.

## 1. Resposta curta

**No caminho principal não há messageria.** São duas situações diferentes:

| Trecho | Mecanismo | Tem fila? |
|---|---|---|
| **bot → API** (pegar fonte pendente, devolver mapa) | *polling* HTTP a cada 60 s; a tabela `fonte` é a fila | **não** |
| **bot → modelo de IA** (backend `rolhama`) | enfileira job num canal, acompanha por *long-poll* | **sim**, mas é fila do rolhama, externa ao KDD |

Ou seja: o **processamento pesado** passa por fila; a **ingestão** não.

## 2. bot → API: banco como fila, sem broker

```
systemd: main.py --loop --intervalo 60 --backend rolhama
   ↓ a cada 60 s
GET  /fontes?status_proc=pendente      ← a "fila" é a tabela fonte
PATCH /fontes/{id} {status_proc: processando}
GET  /fontes/{id}/arquivo  →  extrai texto  →  IA  →  mede sentimento
POST /fontes/{id}/mapas                ← marca processado (+ aprovada)
```

Não há broker: nada de RabbitMQ, Redis ou Kafka. O estado da fila é a coluna
`fonte.status_proc` (`pendente → processando → processado | erro`). Em caso de falha o bot
marca `erro`, e o botão "Reprocessar" (aba Fila) devolve para `pendente`.

Isso é o padrão *database-as-queue*, e para **um** consumidor é uma escolha razoável: zero
infraestrutura nova, estado visível no desktop, e a Hostinger não hospedaria broker. Mas ele
só é correto com duas peças que **hoje faltam** — §3.

## 3. ⚠️ Dois furos reais (confirmados no código)

### 3.1 Não há reivindicação atômica

`Pipeline.processar_pendentes()` faz `listar_pendentes()` e **depois**
`atualizar_status(fid, 'processando')` — duas requisições. `fontes_atualizar()` só valida o
valor do status e faz `UPDATE`, sem condição sobre o estado anterior.

Consequência: **dois bots rodando ao mesmo tempo pegam a mesma fonte** e extraem os dois. Os
dados não duplicam (o push SUBSTITUI o mapa da fonte), mas:

- paga-se **duas extrações de LLM**, que é o recurso caro;
- o segundo push sobrescreve o resultado do primeiro.

Hoje só existe um bot (um `kdd_bot.service` na .90), então o furo está **latente**, não
ativo. Ele abre no instante em que se escalar para dois consumidores.

### 3.2 Fonte travada em `processando` não volta

Se o bot morrer no meio (OOM, reinício, queda de rede depois do PATCH), a fonte fica
`processando` **para sempre**:

- não existe coluna de **quando** a reivindicação começou (`fonte` só tem `criado_em`);
- não existe varredura que devolva à fila o que passou do tempo;
- `POST /fontes/{id}/reprocessar` aceita **apenas** `status_proc = 'erro'`, então nem pela
  aba Fila se recupera.

A fonte simplesmente **sai da fila sem ter sido processada**, silenciosamente. Com extração
local de 4–6 min por documento (CPU, sem GPU), a janela para isso acontecer não é pequena.

## 4. bot → IA: aqui existe fila de verdade

O backend `rolhama` (`bot/kdd_bot/ia/rolhama_backend.py`) **não** bate direto no Ollama: o
slot é único e colidiria com os outros consumidores da máquina. Em vez disso:

```
ClientAPI.enqueue(blob cifrado)        → POST /canal/{n}/job → UUID do job
ClientAPI.response(job, wait=30)       → long-poll de 30 s, repetido até 3600 s
worker rolhama (thread única)          → executa UM job por vez e publica a resposta
```

- `webapi.py` cuida do transporte e do MAC de autenticação (`K_auth` por canal);
- `bdd.py` cifra o payload ponta a ponta (ChaCha20-Poly1305 por `(part, canal)`);
- canal **505** é o reservado ao KDD;
- a fila aceita vários jobs — não há mais o `409`/`remove()` do bddphp antigo.

Essa fila **não é do KDD**: é infraestrutura do rolhama, que o KDD consome como cliente.
Se o rolhama cair, o bot espera e depois marca a fonte como `erro`.

## 5. O que fazer — em ordem de custo

1. **Reivindicação condicional** (resolve §3.1). `UPDATE fonte SET status_proc='processando'
   WHERE id=? AND status_proc='pendente'`, e o bot checa `rowCount()`: 0 significa que outro
   consumidor pegou antes, e ele passa para a próxima. Uma linha de SQL e uma checagem no
   cliente; nenhuma mudança de arquitetura.
2. **Prazo de validade + varredura** (resolve §3.2). Coluna com o instante da reivindicação
   e uma regra que devolve a `pendente` o que está `processando` há mais que N minutos.
   Junto com o item 1, dá uma fila **confiável sem broker**.
3. **Broker de verdade**. Só se houver vários bots em paralelo ou várias origens de
   ingestão. Hoje seria peso sem retorno, e a Hostinger não hospeda o broker.

Recomendação: **1 e 2**. São pequenos, cabem numa migration e em dois trechos de código, e
fecham os dois furos. O item 3 fica para quando a escala pedir.

🟡 **PENDENTE**: nada disso foi implementado — este documento é o diagnóstico.
