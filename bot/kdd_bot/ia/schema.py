"""Esquema e instruções compartilhados pelos backends de IA.

A saída tem que casar com o payload da API:
- PATCH /fontes/{id}        → { "areas": [str] }            (áreas inferidas da fonte)
- POST  /fontes/{id}/mapas  → { "conceitos": [...], "proposicoes": [...] }
"""
from __future__ import annotations

import re
from typing import Any

# Tipos grossos de conceito (espelha KDD_TIPOS_CONCEITO em api/src/valor.php; entram no
# cálculo do VALOR da proposição — docs/valor-conhecimento.md §3).
TIPOS_CONCEITO = frozenset({"entidade", "classe", "processo", "atributo", "outro"})

# Idioma e país (docs/idioma-pais.md). Espelha kdd_idioma_valido/kdd_pais_valido em
# api/src/idioma.php: idioma é SUPERFÍCIE (vive no rótulo), país pode mudar o SENTIDO
# (entra na identidade do conceito). A API revalida tudo; aqui é só para não empurrar lixo.
_RE_IDIOMA = re.compile(r"^[a-z]{2,3}(-[A-Za-z0-9]{2,8})?$")
_RE_PAIS = re.compile(r"^[A-Z]{2}$")


def _idioma(valor: Any) -> str:
    """Tag de idioma válida, ou '' (aí a API usa o padrão da fonte)."""
    t = str(valor or "").strip()
    return t if _RE_IDIOMA.match(t) else ""


def _pais(valor: Any) -> str:
    """Código de país em maiúsculas, ou '' = universal."""
    c = str(valor or "").strip().upper()
    return c if _RE_PAIS.match(c) else ""

# JSON Schema do "mapa" que pedimos à IA (usado como tool input no Claude e como
# contrato no prompt do Ollama).
MAPA_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "areas": {
            "type": "array",
            "description": "Áreas do conhecimento da FONTE como um todo (ex.: Futebol, Jornalismo).",
            "items": {"type": "string"},
        },
        "conceitos": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "rotulo": {"type": "string", "description": "Como o conceito aparece no texto."},
                    "sentido": {
                        "type": "string",
                        "description": "Definição curta e desambiguante do conceito (a IDENTIDADE é o sentido).",
                    },
                    "tipo": {
                        "type": "string",
                        "enum": ["entidade", "classe", "processo", "atributo", "outro"],
                        "description": (
                            "Classe grossa do conceito: 'entidade' (nome próprio: pessoa, "
                            "organização, lugar, produto, obra), 'classe' (categoria, tipo, "
                            "classificação), 'processo' (ação, evento, método), 'atributo' "
                            "(propriedade, medida, valor), 'outro'."
                        ),
                    },
                    "idioma": {
                        "type": "string",
                        "description": (
                            "Idioma do RÓTULO, tag estilo BCP-47 (pt-BR, pt-PT, en, es-AR). "
                            "É só a língua da palavra; não muda o conceito."
                        ),
                    },
                    "pais": {
                        "type": "string",
                        "description": (
                            "Código ISO de 2 letras (BR, PT) APENAS quando o conceito só faz "
                            "sentido naquele país — instituto jurídico, tributo, documento, "
                            "órgão, norma (ex.: CPF, Imposto de Renda). Deixe VAZIO para "
                            "conceito universal, que é o caso comum."
                        ),
                    },
                    "areas": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["rotulo", "sentido"],
            },
        },
        "proposicoes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "origem_rotulo": {"type": "string"},
                    "relacao": {"type": "string", "description": "Verbo/relação curta (ex.: 'fundado_em')."},
                    "destino_rotulo": {"type": "string"},
                    "destino_sentido": {"type": "string"},
                    "pais": {
                        "type": "string",
                        "description": (
                            "Código ISO de 2 letras APENAS quando a relação só vale naquele "
                            "país (ex.: maioridade penal -> 18 anos). Vazio = vale em geral."
                        ),
                    },
                    "relacao_en": {
                        "type": "string",
                        "description": (
                            "A MESMA relação traduzida para o inglês, no presente da 3ª "
                            "pessoa (explora -> exploits, protege -> protects, é um -> is a). "
                            "A análise de sentimento roda sobre o inglês, onde as bases são "
                            "melhores — sem isto a proposição fica sem análise."
                        ),
                    },
                },
                "required": ["origem_rotulo", "relacao", "destino_rotulo"],
            },
        },
    },
    "required": ["areas", "conceitos", "proposicoes"],
}

SYSTEM = (
    "Você extrai MAPAS CONCEITUAIS no estilo de Novak a partir de um texto. "
    "Princípios: (1) a IDENTIDADE de um conceito é o seu SENTIDO, não o rótulo — "
    "dê sempre um 'sentido' curto e desambiguante; rótulos iguais com sentidos "
    "diferentes são conceitos diferentes (homônimos). (2) Proposições são triplas "
    "conceito-origem → relação → conceito-destino, com relação curta. (3) Liste as "
    "áreas do conhecimento da fonte. (4) Classifique cada conceito em 'tipo': "
    "entidade (nome próprio), classe (categoria/classificação), processo (ação/evento), "
    "atributo (propriedade/medida) ou outro. (5) Use relações ESPECÍFICAS: ou um verbo de "
    "ação ('desenvolveu', 'protege contra', 'executa'), ou um verbo de HIERARQUIA — "
    "pertencer, ser, estar, incluir (e conter, compor, fazer parte de) — que diz a que "
    "categoria o conceito pertence. As duas formas valem muito; a hierarquia é o esqueleto "
    "do mapa. EVITE associações vazias ('relaciona-se com', 'associado a', 'tem'), que não "
    "dizem nem o que o conceito é nem a que pertence. Uma tripla entidade + verbo + "
    "classificação é a de maior valor no armazém. "
    "(6) IDIOMA e PAÍS são coisas DIFERENTES e é fácil confundir: TRADUZIR é o MESMO "
    "conceito com outro rótulo noutro idioma (Porta/Door/Puerta: um conceito, três "
    "rótulos) — informe isso em 'idioma'. Já uma instituição, tributo, documento, órgão ou "
    "norma que só existe num país é OUTRO conceito, não tradução: 'Imposto de Renda' (BR) e "
    "o equivalente português são institutos distintos — informe o 'pais'. Preencha 'pais' SÓ "
    "nesse caso; a maioria dos conceitos é universal e fica com o campo vazio. "
    "(7) Para CADA proposição, traduza a relação para o inglês em 'relacao_en' (3ª pessoa do "
    "presente: explora -> exploits, protege -> protects, é um -> is a). A análise de "
    "sentimento da proposição roda sobre o inglês, onde as bases são melhores. "
    "Seja fiel ao texto; não invente fatos."
)


def instrucao_usuario(titulo: str, texto: str) -> str:
    return (
        f"Título da fonte: {titulo}\n\n"
        "Extraia o mapa conceitual do texto a seguir, devolvendo áreas, conceitos "
        "(com rótulo, sentido e áreas) e proposições.\n\n"
        f"=== TEXTO ===\n{texto}"
    )


def normalizar(mapa: dict[str, Any]) -> dict[str, Any]:
    """Garante as três chaves e tipos básicos, descartando entradas inválidas.

    Defensivo contra LLMs (mesmo com ``format=json`` a *forma* não é garantida):
    a raiz pode não ser objeto e itens de conceitos/proposições podem vir como
    strings em vez de dicts — nesses casos descartamos em vez de estourar.
    """
    if not isinstance(mapa, dict):
        mapa = {}
    areas = [str(a).strip() for a in (mapa.get("areas") or []) if str(a).strip()]

    conceitos = []
    for c in mapa.get("conceitos") or []:
        if not isinstance(c, dict):
            continue
        rotulo = str(c.get("rotulo", "")).strip()
        if not rotulo:
            continue
        areas_c = c.get("areas") or []
        if not isinstance(areas_c, list):
            areas_c = []
        item_c = {
            "rotulo": rotulo,
            "sentido": str(c.get("sentido", "")).strip() or rotulo,
            "areas": [str(a).strip() for a in areas_c if str(a).strip()],
        }
        tipo = str(c.get("tipo", "")).strip().lower()
        if tipo in TIPOS_CONCEITO:
            item_c["tipo"] = tipo
        if idioma := _idioma(c.get("idioma")):
            item_c["idioma"] = idioma
        if pais := _pais(c.get("pais")):
            item_c["pais"] = pais
        conceitos.append(item_c)

    proposicoes = []
    for p in mapa.get("proposicoes") or []:
        if not isinstance(p, dict):
            continue
        o, r, d = (str(p.get(k, "")).strip() for k in ("origem_rotulo", "relacao", "destino_rotulo"))
        if not (o and r and d):
            continue
        item = {"origem_rotulo": o, "relacao": r, "destino_rotulo": d}
        ds = str(p.get("destino_sentido", "")).strip()
        if ds:
            item["destino_sentido"] = ds
        if pais := _pais(p.get("pais")):
            item["pais"] = pais
        rel_en = str(p.get("relacao_en", "")).strip()
        if rel_en:
            item["relacao_en"] = rel_en
        proposicoes.append(item)

    return {"areas": areas, "conceitos": conceitos, "proposicoes": proposicoes}
