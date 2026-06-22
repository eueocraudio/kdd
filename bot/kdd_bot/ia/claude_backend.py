"""Backend de nuvem: Claude (Anthropic SDK), extração estruturada via tool use.

Decisão de projeto: modelo padrão ``claude-sonnet-4-6`` (configurável). Usamos
*tool use* com ``tool_choice`` forçado para obter JSON que casa com MAPA_SCHEMA,
e ``messages.stream`` para aguentar saídas longas sem estourar timeout.
"""
from __future__ import annotations

from typing import Any

from anthropic import Anthropic

from .schema import MAPA_SCHEMA, SYSTEM, instrucao_usuario

_TOOL = {
    "name": "registrar_mapa",
    "description": "Registra o mapa conceitual extraído do texto.",
    "input_schema": MAPA_SCHEMA,
}


class ClaudeBackend:
    nome = "claude"

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-6") -> None:
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY ausente para o backend Claude.")
        self._client = Anthropic(api_key=api_key)
        self._model = model

    def extrair_mapa(self, titulo: str, texto: str) -> dict[str, Any]:
        with self._client.messages.stream(
            model=self._model,
            max_tokens=8000,
            system=SYSTEM,
            tools=[_TOOL],
            tool_choice={"type": "tool", "name": "registrar_mapa"},
            messages=[{"role": "user", "content": instrucao_usuario(titulo, texto)}],
        ) as stream:
            final = stream.get_final_message()

        for bloco in final.content:
            if getattr(bloco, "type", None) == "tool_use" and bloco.name == "registrar_mapa":
                return dict(bloco.input)
        raise RuntimeError("Claude não retornou o tool_use 'registrar_mapa'.")
