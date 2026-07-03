# Catálogo de trilhas — termos/paths conhecidos (Passo 1)

## O que é

`api/data/catalogo_trilhas.json` é um catálogo **versionado e curável em PR** de termos
técnicos e caminhos de sistema (Linux/Windows) que **valem como conceito por si só**,
organizados por trilha do app hacker (`trilhas.<slug> = [termos...]`, slug casa com
`trilha.slug` do cursohacker).

A divisão de trabalho combinada com o site (cursohacker):

- **Passo 1 (este documento — bot do KDD):** ao processar uma fonte, termos do catálogo
  encontrados no texto são **auto-adicionados** como conceitos do mapa (não dependem de a
  IA tê-los citado). A fonte continua passando pela aprovação humana normal — a certeza só
  sobe quando o validador aprova a fonte.
- **Passo 2 (já existe, no site):** paths/termos NOVOS (fora do catálogo) detectados na
  transcrição viram **sugestões** na aba KDD do `prof/aula_ia.php` (adicionar/ignorar);
  os aceitos são candidatos a entrar no catálogo por PR.

## Endpoint

`GET /catalogo` (exige token, como as demais leituras) → devolve o JSON do catálogo
(`{_meta, trilhas}`). `404` se o arquivo não existir no deploy. O bot consome por aqui —
o arquivo NÃO é empacotado no deploy do bot (a API é a fonte da verdade).

## Regras de casamento (bot, `kdd_bot/catalogo.py`)

O matching roda sobre o texto extraído da fonte (mesmo texto que vai à IA), com o
catálogo achatado em `termo → [slugs de trilha]` (a união das trilhas; a trilha NÃO
entra na identidade do conceito):

- **Paths** (termo contém `/` ou `\`): busca por **substring, case-sensitive**
  (ex.: `/etc/passwd` casa em "cat /etc/passwd"; `/ETC/PASSWD` não casa).
- **Termos** (demais): **palavra inteira, case-insensitive**, com lookaround
  `(?<!\w)term(?!\w)` — `cron` NÃO casa dentro de `crontab`; `ssh` casa `SSH`.

Cada termo casado vira um conceito no formato do `MAPA_SCHEMA`:

- `rotulo` = o termo como está no catálogo;
- `sentido` = **estável e independente de trilha** (é a identidade — mudar o sentido
  criaria conceito novo a cada push):
  - path: `Caminho/arquivo de sistema conhecido: <termo>`
  - termo: `Termo técnico do catálogo de trilhas: <termo>`
- `areas` = `[]` (o vínculo de área da fonte já vem do contexto; trilha não é área).

Sem proposições — o conceito entra "solto" e as relações vêm da IA ou da curadoria.

## Integração no pipeline

- O catálogo é buscado **uma vez por execução** do bot (cache em memória no `Pipeline`).
  Falha ao buscar (ex.: API antiga sem a rota) → WARNING e segue sem catálogo (o
  processamento normal não pode morrer por causa do extra).
- **Modo fonte única:** os conceitos casados são fundidos ao mapa da IA antes do push
  (dedup por sentido — se a IA já trouxe o mesmo sentido, não duplica; o push da API
  também é idempotente por sentido, é só para o log ficar honesto).
- **Modo seções:** os casamentos são acumulados sobre TODAS as seções e enviados num
  push extra (`conceitos` só) ao final — apenas se alguma seção foi processada.

## Verificação

`bot/exemplos/teste_catalogo.py` (padrão do repo: script que bate na API real):
1. offline: casos do matcher (path case-sensitive, palavra-inteira, `cron`×`crontab`);
2. e2e sem LLM: sobe fonte de texto com termos do catálogo numa API local, roda o
   `Pipeline` com uma IA *stub* (mapa vazio) e confere via `GET /fontes/{id}/mapa`
   que os conceitos do catálogo foram criados.
