"""Backend que usa o Claude Code (CLI `claude`) em modo print/headless.

Útil para testar o pipeline sem uma ANTHROPIC_API_KEY própria: reaproveita a
sessão/credencial do Claude Code já instalado na máquina. Pede saída estruturada
via `--json-schema`, que o CLI devolve no campo `structured_output`.
"""
from __future__ import annotations

import json
import subprocess
import tempfile
from typing import Any

from .schema import MAPA_SCHEMA, SYSTEM, instrucao_usuario


class CliBackend:
    nome = "cli"

    def __init__(self, model: str = "", timeout: float = 900.0) -> None:
        self._model = model
        self._timeout = timeout

    def extrair_mapa(self, titulo: str, texto: str) -> dict[str, Any]:
        prompt = SYSTEM + "\n\n" + instrucao_usuario(titulo, texto)
        cmd = [
            "claude", "-p",
            "--output-format", "json",
            "--json-schema", json.dumps(MAPA_SCHEMA, ensure_ascii=False),
        ]
        if self._model:
            cmd += ["--model", self._model]

        # roda num diretório neutro para não carregar CLAUDE.md/memória do projeto
        with tempfile.TemporaryDirectory() as cwd:
            proc = subprocess.run(
                cmd, input=prompt, capture_output=True, text=True,
                timeout=self._timeout, cwd=cwd,
            )
        if proc.returncode != 0:
            raise RuntimeError(f"claude CLI falhou ({proc.returncode}): {proc.stderr[:500]}")

        try:
            envelope = json.loads(proc.stdout)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"CLI devolveu saída não-JSON: {e}; saída: {proc.stdout[:300]}") from e

        if envelope.get("is_error"):
            raise RuntimeError(f"CLI retornou erro: {envelope.get('result')!r}")

        saida = envelope.get("structured_output")
        if not isinstance(saida, dict):
            raise RuntimeError("CLI não retornou 'structured_output' conforme o schema.")
        return saida
