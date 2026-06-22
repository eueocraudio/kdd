"""Esquema e instruções compartilhados pelos backends de IA.

A saída tem que casar com o payload da API:
- PATCH /fontes/{id}        → { "areas": [str] }            (áreas inferidas da fonte)
- POST  /fontes/{id}/mapas  → { "conceitos": [...], "proposicoes": [...] }
"""
from __future__ import annotations

from typing import Any

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
    "áreas do conhecimento da fonte. Seja fiel ao texto; não invente fatos."
)


def instrucao_usuario(titulo: str, texto: str) -> str:
    return (
        f"Título da fonte: {titulo}\n\n"
        "Extraia o mapa conceitual do texto a seguir, devolvendo áreas, conceitos "
        "(com rótulo, sentido e áreas) e proposições.\n\n"
        f"=== TEXTO ===\n{texto}"
    )


def normalizar(mapa: dict[str, Any]) -> dict[str, Any]:
    """Garante as três chaves e tipos básicos, descartando entradas inválidas."""
    areas = [str(a).strip() for a in (mapa.get("areas") or []) if str(a).strip()]

    conceitos = []
    for c in mapa.get("conceitos") or []:
        rotulo = str(c.get("rotulo", "")).strip()
        if not rotulo:
            continue
        conceitos.append({
            "rotulo": rotulo,
            "sentido": str(c.get("sentido", "")).strip() or rotulo,
            "areas": [str(a).strip() for a in (c.get("areas") or []) if str(a).strip()],
        })

    proposicoes = []
    for p in mapa.get("proposicoes") or []:
        o, r, d = (str(p.get(k, "")).strip() for k in ("origem_rotulo", "relacao", "destino_rotulo"))
        if not (o and r and d):
            continue
        item = {"origem_rotulo": o, "relacao": r, "destino_rotulo": d}
        ds = str(p.get("destino_sentido", "")).strip()
        if ds:
            item["destino_sentido"] = ds
        proposicoes.append(item)

    return {"areas": areas, "conceitos": conceitos, "proposicoes": proposicoes}
