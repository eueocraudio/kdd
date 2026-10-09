"""Servidor MCP do KDD — o armazém como ferramentas para agentes de IA.

Ver docs/mcp-servidor.md.
"""
from .config import Config
from .servidor import construir

__all__ = ["Config", "construir"]
