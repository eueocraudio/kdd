"""Análise de SENTIMENTO da proposição (docs/sentimento.md).

⚠️ MEDIDO EM INGLÊS, NUNCA EM PORTUGUÊS. Léxico e modelo de sentimento em pt-BR têm base
pobre e erram muito; as bases maduras (VADER, Hu & Liu, SentiWordNet, pattern) são em inglês.
A proposição é traduzida para a forma canônica inglesa e a medição acontece lá.

⚠️ RODA NO BOT, não na API. Mesma divisão da camada vetorial: Python analisa, PHP guarda e
agrega. A Hostinger não tem Python.

Pacotes usados (os padrões de mercado para sentimento em inglês):
  · **vaderSentiment** — polaridade. É o mais usado para inglês (também embarcado no NLTK),
    lexicon+regras, determinístico, sem baixar modelo.
  · **TextBlob** — subjetividade (fato × juízo de valor). `.sentiment` funciona SEM baixar
    corpora do NLTK, então não há passo extra no deploy.

⚠️ POR QUE AINDA EXISTE UM AJUSTE DE DOMÍNIO. Medido nas proposições do próprio armazém
(ver `autoteste()`), o VADER acerta ~7/13 e erra exatamente nos casos de domínio, porque
pontua o VOCABULÁRIO da frase e não a RELAÇÃO:

  · "ransomware encrypts files"      VADER  0.00  → devia ser negativo
  · "firewall blocks traffic"        VADER -0.23  → "blocks" é ruim em inglês geral, mas
                                                     bloquear é bom em segurança
  · "patch fixes vulnerability"      VADER -0.23  → o substantivo "vulnerability" arrasta a
                                                     frase, embora a relação (fixes) seja boa

Então: a polaridade do VERBO DA RELAÇÃO manda quando é conhecida (é ela que diz se a origem
ajuda ou prejudica o destino); o VADER entra como sinal da frase inteira quando o verbo não
está no mapa. A subjetividade é 100% TextBlob, que acertou 13/13.
"""
from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)

try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    from textblob import TextBlob
    _DISPONIVEL = True
except ImportError:  # pragma: no cover
    _DISPONIVEL = False
    log.warning("vaderSentiment/textblob ausentes: sentimento não será medido "
                "(pip install vaderSentiment textblob)")

_vader: Any = None


def disponivel() -> bool:
    """True se os pacotes de análise estão instalados."""
    return _DISPONIVEL


def _analisador():
    global _vader
    if _vader is None:
        _vader = SentimentIntensityAnalyzer()
    return _vader


# ── Tradução de apoio pt→en do VERBO da relação ──
# Usada quando a IA não mandou `relacao_en`. O que não estiver aqui e não vier da IA fica
# SEM TRADUÇÃO, e aí o sentimento sai NÃO MEDIDO — de propósito: a lacuna tem de ficar
# visível em vez de virar um zero silencioso que parece "neutro".
RELACAO_PT_EN: dict[str, str] = {
    # hierarquia
    "e": "is", "e um": "is a", "e uma": "is a", "e um tipo de": "is a type of",
    "tipo de": "type of", "e instancia de": "is an instance of",
    "e exemplo de": "is an example of", "pertence a": "belongs to",
    "pertence ao": "belongs to", "membro de": "member of", "parte de": "part of",
    "e parte de": "is part of", "faz parte de": "is part of", "compoe": "composes",
    "composto por": "composed of", "contem": "contains", "inclui": "includes",
    "abrange": "encompasses", "esta em": "is in", "esta": "is",
    "classifica-se como": "is classified as", "categoria de": "category of",
    # vagas
    "tem": "has", "possui": "has", "relaciona-se com": "relates to",
    "associado a": "associated with", "ligado a": "linked to", "refere-se a": "refers to",
    # ação neutra
    "desenvolveu": "developed", "criou": "created", "usa": "uses", "executa": "executes",
    "implementa": "implements", "define": "defines", "descreve": "describes",
    "transporta": "transports", "armazena": "stores", "processa": "processes",
    # negativas (prejudicam o destino)
    "explora": "exploits", "compromete": "compromises", "ataca": "attacks",
    "viola": "violates", "corrompe": "corrupts", "vaza": "leaks", "danifica": "damages",
    "destroi": "destroys", "burla": "bypasses", "contorna": "circumvents",
    "infecta": "infects", "sequestra": "hijacks", "intercepta": "intercepts",
    "falsifica": "spoofs", "degrada": "degrades", "enfraquece": "weakens",
    "expoe": "exposes", "ameaca": "threatens", "prejudica": "harms", "quebra": "breaks",
    "nega": "denies", "sobrecarrega": "overloads", "rouba": "steals", "frauda": "defrauds",
    "espiona": "spies on", "abusa": "abuses", "envenena": "poisons",
    # positivas (beneficiam o destino)
    "protege": "protects", "protege contra": "protects against", "defende": "defends",
    "mitiga": "mitigates", "corrige": "fixes", "previne": "prevents", "evita": "avoids",
    "autentica": "authenticates", "valida": "validates", "verifica": "verifies",
    "reforca": "strengthens", "fortalece": "strengthens", "isola": "isolates",
    "cifra": "encrypts", "criptografa": "encrypts", "anonimiza": "anonymizes",
    "monitora": "monitors", "detecta": "detects", "bloqueia": "blocks",
    "filtra": "filters", "melhora": "improves", "otimiza": "optimizes",
    "garante": "ensures", "assegura": "ensures", "preserva": "preserves",
    "recupera": "recovers", "restaura": "restores", "trata": "treats",
    "permite": "enables", "habilita": "enables", "sustenta": "supports",
    "apoia": "supports", "audita": "audits",
    # juízo de valor
    "e melhor que": "is better than", "e pior que": "is worse than",
    "deve usar": "should use", "recomenda": "recommends", "deveria": "should",
}

# Polaridade do VERBO, que é o que diz se a origem ajuda ou prejudica o destino.
# Tem precedência sobre o VADER porque o VADER pontua a frase, não a relação.
VERBO_NEGATIVO = frozenset({
    "exploits", "compromises", "attacks", "violates", "corrupts", "leaks", "damages",
    "destroys", "bypasses", "circumvents", "infects", "hijacks", "intercepts", "spoofs",
    "degrades", "weakens", "exposes", "threatens", "harms", "breaks", "denies",
    "overloads", "steals", "defrauds", "spies on", "abuses", "poisons", "disrupts",
    "escalates", "tampers with", "crashes", "disables",
})
VERBO_POSITIVO = frozenset({
    "protects", "protects against", "defends", "mitigates", "fixes", "patches",
    "prevents", "avoids", "authenticates", "validates", "verifies", "strengthens",
    "hardens", "isolates", "encrypts", "anonymizes", "monitors", "detects", "blocks",
    "filters", "improves", "optimizes", "ensures", "guarantees", "preserves",
    "recovers", "restores", "treats", "heals", "enables", "supports", "audits",
    "secures", "sanitizes", "backs up",
})

# ⚠️ AGENTE MALICIOSO INVERTE O VERBO. O mesmo verbo muda de valência conforme QUEM age:
# "backup encrypts files" é bom, "ransomware encrypts files" é péssimo. "firewall monitors
# traffic" é bom, "attacker monitors traffic" é espionagem. Nenhum léxico resolve isso
# olhando só o verbo — mas a origem maliciosa é um padrão frequente e barato de detectar.
# Fora desta lista, a ambiguidade fica para a IA, que mede por fonte e vê o contexto.
ORIGEM_MALICIOSA = frozenset({
    "malware", "ransomware", "spyware", "adware", "rootkit", "trojan", "virus", "worm",
    "botnet", "keylogger", "attacker", "adversary", "intruder", "phisher", "exploit kit",
    "threat actor", "cracker", "backdoor", "payload", "dropper", "stealer",
})


def _origem_maliciosa(origem_en: str) -> bool:
    """True se a origem é um agente malicioso conhecido (inverte o verbo positivo)."""
    t = (origem_en or "").strip().lower()
    if not t:
        return False
    return any(termo in t for termo in ORIGEM_MALICIOSA)


def _normalizar_pt(relacao: str) -> str:
    """Espelha kdd_normalizar_relacao() do PHP: minúsculas, sem acento, '_' vira espaço."""
    r = (relacao or "").strip().lower().replace("_", " ")
    for de, para in (("á", "a"), ("à", "a"), ("ã", "a"), ("â", "a"), ("é", "e"), ("ê", "e"),
                     ("í", "i"), ("ó", "o"), ("õ", "o"), ("ô", "o"), ("ú", "u"),
                     ("ü", "u"), ("ç", "c")):
        r = r.replace(de, para)
    return " ".join(r.split())


def relacao_em_ingles(relacao: str, relacao_en: str | None = None) -> str:
    """Forma inglesa do verbo: a da IA quando vem, senão a tradução de apoio. '' se não há."""
    if relacao_en and relacao_en.strip():
        return relacao_en.strip().lower()
    return RELACAO_PT_EN.get(_normalizar_pt(relacao), "")


def analisar(relacao: str, relacao_en: str | None = None,
             origem_en: str = "", destino_en: str = "") -> dict[str, Any] | None:
    """Mede a proposição. ``None`` = não medida (sem tradução ou sem os pacotes).

    Devolve ``{polaridade, subjetividade, relacao_en, texto_analisado, motor}``.
    """
    if not _DISPONIVEL:
        return None

    rel_en = relacao_em_ingles(relacao, relacao_en)
    if not rel_en:
        return None   # sem forma inglesa não se mede — e não se finge neutro

    texto = " ".join(p for p in (origem_en.strip(), rel_en, destino_en.strip()) if p)

    # Subjetividade: TextBlob (13/13 no autoteste — é o que ele faz bem).
    subjetividade = float(TextBlob(texto).sentiment.subjectivity)

    # Polaridade: o VERBO manda quando é conhecido; senão o VADER sobre a frase.
    if rel_en in VERBO_NEGATIVO:
        polaridade, motor = -1.0, "verbo"
    elif rel_en in VERBO_POSITIVO:
        # agente malicioso inverte: "ransomware encrypts files" não é benefício
        if _origem_maliciosa(origem_en):
            polaridade, motor = -1.0, "verbo+origem"
        else:
            polaridade, motor = 1.0, "verbo"
    else:
        polaridade = float(_analisador().polarity_scores(texto)["compound"])
        motor = "vader"

    return {
        "polaridade": round(max(-1.0, min(1.0, polaridade)), 2),
        "subjetividade": round(max(0.0, min(1.0, subjetividade)), 2),
        "relacao_en": rel_en,
        "texto_analisado": texto,
        "motor": motor,
    }


def enriquecer_proposicoes(proposicoes: list[dict[str, Any]],
                           rotulos_en: dict[str, str] | None = None) -> int:
    """Anota polaridade/subjetividade/relacao_en em cada proposição, in place.

    ``rotulos_en`` mapeia rótulo original → rótulo em inglês, quando conhecido (melhora o
    texto analisado). Devolve quantas foram medidas.
    """
    rotulos_en = rotulos_en or {}
    medidas = 0
    for p in proposicoes:
        r = analisar(
            str(p.get("relacao", "")),
            p.get("relacao_en"),
            rotulos_en.get(str(p.get("origem_rotulo", "")), ""),
            rotulos_en.get(str(p.get("destino_rotulo", "")), ""),
        )
        if r is None:
            continue
        p["polaridade"] = r["polaridade"]
        p["subjetividade"] = r["subjetividade"]
        p["relacao_en"] = r["relacao_en"]
        medidas += 1
    return medidas


# ── Autoteste: as proposições que motivaram o ajuste de domínio ──
CASOS_AUTOTESTE: list[tuple[str, str, str, int, bool]] = [
    # (origem_en, relacao_pt, destino_en, polaridade esperada, é juízo?)
    ("malware", "explora", "vulnerability", -1, False),
    ("attacker", "burla", "authentication", -1, False),
    ("SQL injection", "compromete", "database", -1, False),
    ("backup", "protege", "data", 1, False),
    ("firewall", "bloqueia", "traffic", 1, False),
    ("encryption", "protege", "privacy", 1, False),
    ("patch", "corrige", "vulnerability", 1, False),
    ("TCP", "é um", "transport protocol", 0, False),
    ("Anthropic", "desenvolveu", "Claude", 0, False),
    ("Claude", "pertence a", "language models", 0, False),
    # Elogio comparativo: a polaridade POSITIVA está correta (elogia o Linux). O que este
    # caso existe para testar é a SUBJETIVIDADE alta — é juízo de valor, não fato.
    ("Linux", "é melhor que", "Windows", 1, True),
    # Mesmo verbo, origem maliciosa: tem de inverter.
    ("ransomware", "criptografa", "files", -1, False),
    ("backup", "criptografa", "files", 1, False),
]


def autoteste() -> tuple[int, int]:
    """Roda os casos de referência. Devolve (acertos de polaridade, total)."""
    if not _DISPONIVEL:
        print("pacotes ausentes: pip install vaderSentiment textblob")
        return (0, 0)
    acertos = 0
    print(f"{'proposição (EN)':<44} {'esp':>4} {'pol':>6} {'subj':>5} {'motor':>6}  ok")
    print("-" * 78)
    for origem, rel, destino, esperado, juizo in CASOS_AUTOTESTE:
        r = analisar(rel, None, origem, destino)
        if r is None:
            print(f"{origem + ' ' + rel + ' ' + destino:<44} {esperado:>4} {'—':>6} "
                  f"{'—':>5} {'—':>6}  NÃO MEDIDO")
            continue
        sinal = 0 if abs(r["polaridade"]) < 0.25 else (1 if r["polaridade"] > 0 else -1)
        ok = sinal == esperado
        acertos += ok
        marca = "sim" if ok else "NAO"
        if (r["subjetividade"] >= 0.5) != juizo:
            marca += " (subj?)"
        print(f"{r['texto_analisado']:<44} {esperado:>4} {r['polaridade']:>6.2f} "
              f"{r['subjetividade']:>5.2f} {r['motor']:>6}  {marca}")
    print("-" * 78)
    print(f"polaridade: {acertos}/{len(CASOS_AUTOTESTE)}")
    return (acertos, len(CASOS_AUTOTESTE))


if __name__ == "__main__":
    autoteste()
