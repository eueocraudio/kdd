"""Servidor MCP do KDD — expõe o armazém como ferramentas para agentes de IA.

Spec: docs/mcp-servidor.md. Adaptador FINO sobre a Web API (§2): nenhuma regra de domínio
aqui. Toda ferramenta devolve o JSON da API, para o modelo ler os campos da camada de valor
(valor, relacao_classe, esteio, similares).

Escrita só é REGISTRADA quando KDD_MCP_ESCRITA=1 e há KDD_TOKEN_VALIDADOR — o modelo nem vê
as ferramentas que não pode usar.
"""
from __future__ import annotations

import logging
import sys
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from .cliente import KddCliente, KddErro
from .config import Config

log = logging.getLogger("kdd.mcp")

INSTRUCOES = """\
Este servidor dá acesso ao armazém KDD: conhecimento extraído de documentos e representado
como MAPAS CONCEITUAIS (no estilo de Novak), com curadoria humana.

Como o armazém pensa:
- A IDENTIDADE de um conceito é o seu SENTIDO, não o rótulo. Rótulos iguais com sentidos
  diferentes são conceitos DIFERENTES (homônimos, ex.: "Botafogo" time x bairro).
- Uma PROPOSIÇÃO é a tripla origem -[relação]-> destino.
- Cada proposição tem um VALOR de 0 a 100: combina a estrutura da tripla (tipo dos conceitos
  e classe da relação), o reforço por fontes aprovadas e o esteio dos conceitos. Relações de
  hierarquia (pertencer, ser, estar, incluir) reforçam a ligação; associações vagas
  ("relaciona-se com") valem pouco. Use o valor para julgar o quanto confiar numa afirmação.
- Um ESTEIO é um conceito que sustenta muitas relações: os pilares do mapa.
- ÁREA é classificação temática N-N, nunca identidade.
- O armazém tem UNIVERSOS PARALELOS: domínios de conhecimento isolados. O MESMO rótulo e o
  MESMO sentido podem existir em cada um, como conceitos diferentes. A identidade real é
  (universo, sentido). Proposição nunca cruza universo; o gêmeo de um conceito no universo
  vizinho se acha com obter_contrapartes. Toda ferramenta de leitura aceita 'universo'
  (o slug); sem ele, trabalha no universo 'principal'.

Comece por listar_universos para saber que domínios existem, depois listar_areas ou
listar_esteios para ver o terreno, e buscar_conceitos / obter_conceito para o detalhe.\
"""

# ── anotações ──
LEITURA = ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=False)
ESCRITA = ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=False)


def _erro(e: KddErro) -> dict[str, Any]:
    """Erro vira RESULTADO legível, não exceção: o modelo lê e decide (spec §6)."""
    return {"erro": str(e)}


def construir(config: Config | None = None) -> MCPServer:
    cfg = config or Config.carregar()
    cliente = KddCliente(cfg)

    servidor = MCPServer(
        name="kdd",
        title="KDD — armazém de mapas conceituais",
        instructions=INSTRUCOES,
        version="1.0.0",
    )

    # ───────────────────────── leitura ─────────────────────────

    @servidor.tool(
        name="listar_areas",
        description="Árvore hierárquica das áreas do conhecimento do armazém (pai → filhos).",
        annotations=LEITURA,
    )
    def listar_areas(universo: str = "") -> dict[str, Any]:
        try:
            return {"areas": cliente.areas(universo=universo)}
        except KddErro as e:
            return _erro(e)

    @servidor.tool(
        name="listar_universos",
        description=(
            "Os UNIVERSOS do armazém: domínios de conhecimento isolados, cada um com seus "
            "próprios conceitos, áreas e fontes. O mesmo rótulo e o mesmo sentido podem "
            "existir em vários, como conceitos diferentes. Use o 'slug' nas outras "
            "ferramentas; sem informar nada, trabalha-se no universo 'principal'."
        ),
        annotations=LEITURA,
    )
    def listar_universos() -> dict[str, Any]:
        try:
            return {"universos": cliente.universos()}
        except KddErro as e:
            return _erro(e)

    @servidor.tool(
        name="obter_contrapartes",
        description=(
            "O MESMO conceito nos OUTROS universos — o gêmeo em universo paralelo. Casa por "
            "rótulo idêntico e por similaridade vetorial. Serve para comparar como dois "
            "domínios tratam a mesma ideia. Não é candidato a fusão: fundir entre universos "
            "é proibido."
        ),
        annotations=LEITURA,
    )
    def obter_contrapartes(conceito_id: int) -> dict[str, Any]:
        try:
            return cliente.contrapartes(conceito_id)
        except KddErro as e:
            return _erro(e)

    @servidor.tool(
        name="buscar_conceitos",
        description=(
            "Busca conceitos por texto do rótulo e/ou por área. Devolve id, sentido, rótulos, "
            "áreas, tipo, grau e esteio de cada um. Sem filtros, lista tudo. Use o id em "
            "obter_conceito para o detalhe com as proposições."
        ),
        annotations=LEITURA,
    )
    def buscar_conceitos(texto: str = "", area_id: str = "", fonte_id: int | None = None,
                         universo: str = "") -> dict[str, Any]:
        """
        Args:
            texto: trecho do rótulo a procurar (busca parcial, ex.: "proto").
            area_id: id da área, ou vários separados por vírgula (união, ex.: "1,4").
            fonte_id: restringe aos conceitos que vieram de um documento.
            universo: slug do universo; vazio = 'principal'.
        """
        try:
            return {"conceitos": cliente.conceitos(q=texto, area=area_id, fonte=fonte_id,
                                                   universo=universo)}
        except KddErro as e:
            return _erro(e)

    @servidor.tool(
        name="obter_conceito",
        description=(
            "Detalhe de um conceito: sentido (a identidade), rótulos, áreas, tipo, esteio, "
            "fontes que o sustentam, as proposições em que participa COM O VALOR de cada uma, "
            "e os conceitos semanticamente semelhantes."
        ),
        annotations=LEITURA,
    )
    def obter_conceito(conceito_id: int) -> dict[str, Any]:
        try:
            return {"conceito": cliente.conceito(conceito_id)}
        except KddErro as e:
            return _erro(e)

    @servidor.tool(
        name="listar_proposicoes",
        description=(
            "Proposições (triplas origem -[relação]-> destino) já ordenadas por VALOR "
            "decrescente. Filtre por conceito para ver só as dele."
        ),
        annotations=LEITURA,
    )
    def listar_proposicoes(conceito_id: int | None = None, universo: str = "") -> dict[str, Any]:
        try:
            return {"proposicoes": cliente.proposicoes(conceito=conceito_id, universo=universo)}
        except KddErro as e:
            return _erro(e)

    @servidor.tool(
        name="listar_esteios",
        description=(
            "Os conceitos-ESTEIO: os que sustentam mais relações no mapa, do maior para o "
            "menor. É o melhor ponto de partida para entender do que o armazém trata."
        ),
        annotations=LEITURA,
    )
    def listar_esteios(limite: int = 20, universo: str = "") -> dict[str, Any]:
        try:
            return {"esteios": cliente.esteios(limite=limite, universo=universo)}
        except KddErro as e:
            return _erro(e)

    @servidor.tool(
        name="ver_constelacao",
        description=(
            "Visão macro do armazém: áreas com contagem de conceitos, PONTES "
            "interdisciplinares (proposições que cruzam áreas) e HOMÔNIMOS (um rótulo com "
            "vários sentidos)."
        ),
        annotations=LEITURA,
    )
    def ver_constelacao(universo: str = "") -> dict[str, Any]:
        try:
            return cliente.constelacao(universo=universo)
        except KddErro as e:
            return _erro(e)

    @servidor.tool(
        name="listar_semelhantes",
        description=(
            "Pares de conceitos semanticamente parecidos, achados por similaridade vetorial. "
            "Como a identidade é o sentido EXATO, dois sentidos quase iguais viram conceitos "
            "distintos — esta é a fila de candidatos a fusão. Vazio se ninguém rodou a "
            "vetorização ainda."
        ),
        annotations=LEITURA,
    )
    def listar_semelhantes(similaridade_minima: float = 0.85, limite: int = 50,
                           escopo: str = "interno") -> dict[str, Any]:
        """
        Args:
            escopo: 'interno' (mesmo universo = candidatos a fusão), 'externo'
                (universos diferentes = contrapartes) ou 'todos'.
        """
        try:
            return {"semelhantes": cliente.similares(minimo=similaridade_minima,
                                                     limite=limite, escopo=escopo)}
        except KddErro as e:
            return _erro(e)

    @servidor.tool(
        name="obter_mapa_da_fonte",
        description=(
            "O mapa conceitual de UM documento: os conceitos e proposições que aquela fonte "
            "introduziu, com valor e certeza."
        ),
        annotations=LEITURA,
    )
    def obter_mapa_da_fonte(fonte_id: int) -> dict[str, Any]:
        try:
            return cliente.mapa_da_fonte(fonte_id)
        except KddErro as e:
            return _erro(e)

    @servidor.tool(
        name="listar_fontes",
        description=(
            "Documentos do armazém e seus dois status independentes: status_proc "
            "(pendente/processando/processado/erro, do bot) e status_aprovacao "
            "(pendente/aprovada/reprovada, do curador humano)."
        ),
        annotations=LEITURA,
    )
    def listar_fontes(status_proc: str = "", status_aprovacao: str = "",
                      universo: str = "") -> dict[str, Any]:
        try:
            return {"fontes": cliente.fontes(status_proc=status_proc,
                                             status_aprovacao=status_aprovacao,
                                             universo=universo)}
        except KddErro as e:
            return _erro(e)

    # ───────────────────── escrita (opcional) ─────────────────────
    # Registradas só com KDD_MCP_ESCRITA=1 + KDD_TOKEN_VALIDADOR (spec §4). Base curada:
    # escrita de agente é opt-in explícito, e nada aqui remove ou altera o que existe.

    if cfg.escrita:
        @servidor.tool(
            name="ingerir_texto",
            description=(
                "Envia um texto como nova FONTE para o armazém. A fonte entra na fila e o bot "
                "extrai o mapa conceitual com IA depois. Informe 'ref' para poder reenviar o "
                "mesmo documento sem duplicar (reenviar atualiza o texto e reprocessa)."
            ),
            annotations=ESCRITA,
        )
        def ingerir_texto(titulo: str, texto: str, contexto: str = "", ref: str = "",
                          universo: str = "") -> dict[str, Any]:
            """
            Args:
                titulo: título do documento.
                texto: o conteúdo a analisar.
                contexto: a "lente" da fonte — vira a área-raiz (ex.: nome do curso).
                ref: chave de idempotência de quem envia (ex.: "aula:42").
                universo: slug do universo de destino; vazio = 'principal'.
            """
            try:
                return cliente.ingerir_texto(titulo=titulo, texto=texto, contexto=contexto,
                                             ref=ref, universo=universo)
            except KddErro as e:
                return _erro(e)

        @servidor.tool(
            name="criar_conceito",
            description=(
                "Cria um conceito por curadoria. O SENTIDO é a identidade DENTRO DO UNIVERSO e "
                "precisa ser único lá: escreva uma definição curta e desambiguante. O tipo "
                "(entidade, classe, processo, atributo) pesa no valor das proposições."
            ),
            annotations=ESCRITA,
        )
        def criar_conceito(sentido: str, rotulo_principal: str,
                           areas: list[str] | None = None, tipo: str = "",
                           universo: str = "") -> dict[str, Any]:
            try:
                return cliente.criar_conceito(sentido=sentido, rotulo_principal=rotulo_principal,
                                              areas=areas, tipo=tipo, universo=universo)
            except KddErro as e:
                return _erro(e)

        @servidor.tool(
            name="criar_proposicao",
            description=(
                "Liga dois conceitos existentes (por id) com uma relação. Prefira um verbo de "
                "ação específico, ou um de hierarquia (pertence a, é um, inclui) — ambos valem "
                "muito. Evite 'relaciona-se com', que vale pouco. Os dois conceitos têm de "
                "estar no MESMO universo: proposição não cruza universo."
            ),
            annotations=ESCRITA,
        )
        def criar_proposicao(origem_id: int, relacao: str, destino_id: int) -> dict[str, Any]:
            try:
                return cliente.criar_proposicao(origem_id=origem_id, relacao=relacao,
                                                destino_id=destino_id)
            except KddErro as e:
                return _erro(e)

    return servidor


def main() -> int:
    # stderr: em stdio o stdout é o CANAL do protocolo — log nele corrompe o JSON-RPC.
    logging.basicConfig(level=logging.INFO, stream=sys.stderr,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        cfg = Config.carregar()
    except RuntimeError as e:
        print(f"Configuração inválida: {e}", file=sys.stderr)
        return 1

    log.info("KDD MCP em %s | escrita: %s", cfg.base_url, "ON" if cfg.escrita else "OFF (leitura)")
    construir(cfg).run(transport="stdio")
    return 0
