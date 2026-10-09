<?php
declare(strict_types=1);

/**
 * SENTIMENTO da proposição — lado da API (docs/sentimento.md).
 *
 * ⚠️ A API **NÃO pontua**. Ela valida, guarda e agrega. Quem mede é o bot
 * (`bot/kdd_bot/sentimento.py`) com **vaderSentiment** + **TextBlob**, sobre a forma
 * INGLESA da proposição. Dois motivos:
 *   1. análise de sentimento em pt-BR tem base pobre e erra muito; as bases maduras são em
 *      inglês, então a proposição é traduzida e medida lá;
 *   2. um único motor de pontuação. Um léxico em PHP aqui divergiria do Python no primeiro
 *      ajuste — mesmo raciocínio pelo qual a fórmula do valor vive só na API.
 * Mesma divisão da camada vetorial: Python analisa, PHP guarda. A Hostinger não tem Python.
 *
 * Dois eixos INDEPENDENTES:
 *   · polaridade    (-1..+1) a relação PREJUDICA ou BENEFICIA o destino
 *   · subjetividade ( 0..1 ) fato verificável × juízo de valor
 *
 * ⚠️ Assimetria central (spec §4): a SUBJETIVIDADE desconta o valor (juízo vale menos como
 * conhecimento que fato); a POLARIDADE **não** — descontar o negativo injetaria viés
 * otimista, e "malware compromete sistema" é conhecimento de primeira.
 *
 * ⚠️ Sem medição, o sentimento sai **não medido**, nunca "neutro": fabricar neutro
 * esconderia a ausência de análise.
 */

/** Peso do desconto de subjetividade no valor (spec §4). */
const KDD_DESCONTO_SUBJETIVIDADE = 0.20;

/** Normaliza polaridade vinda do cliente para [-1,1]; null se não informada. */
function kdd_polaridade_valida($valor): ?float
{
    if ($valor === null || $valor === '' || !is_numeric($valor)) {
        return null;
    }
    return max(-1.0, min(1.0, (float) $valor));
}

/** Normaliza subjetividade vinda do cliente para [0,1]; null se não informada. */
function kdd_subjetividade_valida($valor): ?float
{
    if ($valor === null || $valor === '' || !is_numeric($valor)) {
        return null;
    }
    return max(0.0, min(1.0, (float) $valor));
}

/** Rótulo legível da polaridade, para filtro e UI. */
function kdd_rotulo_polaridade(?float $polaridade): string
{
    if ($polaridade === null) {
        return 'nao_medida';
    }
    if ($polaridade <= -0.25) {
        return 'negativa';
    }
    if ($polaridade >= 0.25) {
        return 'positiva';
    }
    return 'neutra';
}

/**
 * Sentimento agregado de um conjunto de proposições, só sobre fontes APROVADAS
 * (a view cuida disso: reprovar remove a contribuição, igual à certeza).
 *
 * Proposição sem nenhuma fonte que tenha medido sai com polaridade `null` e
 * `origem: 'nao_medido'` — a lacuna fica visível.
 */
function kdd_sentimento_proposicoes(PDO $pdo, array $ids): array
{
    $ids = array_values(array_unique(array_map('intval', $ids)));
    if (!$ids) {
        return [];
    }
    $ph = implode(',', array_fill(0, count($ids), '?'));
    $s  = $pdo->prepare(
        "SELECT proposicao_id, polaridade, subjetividade, fontes_medidas, discordancia
           FROM vw_sentimento_proposicao WHERE proposicao_id IN ($ph)"
    );
    $s->execute($ids);

    $out = [];
    foreach ($s->fetchAll() as $r) {
        $pid     = (int) $r['proposicao_id'];
        $medidas = (int) $r['fontes_medidas'];

        if ($medidas === 0) {
            $out[$pid] = [
                'polaridade' => null, 'subjetividade' => null, 'fontes_medidas' => 0,
                'discordancia' => 0.0, 'rotulo' => 'nao_medida', 'origem' => 'nao_medido',
            ];
            continue;
        }

        $pol = (float) $r['polaridade'];
        $out[$pid] = [
            'polaridade'     => round($pol, 2),
            'subjetividade'  => $r['subjetividade'] !== null ? round((float) $r['subjetividade'], 2) : 0.0,
            'fontes_medidas' => $medidas,
            // alto = as fontes DIVERGEM no enquadramento da mesma afirmação (informação de
            // curadoria, não ruído a esconder)
            'discordancia'   => round((float) $r['discordancia'], 2),
            'rotulo'         => kdd_rotulo_polaridade($pol),
            'origem'         => 'fontes',
        ];
    }
    return $out;
}

/** Filtro ?polaridade=negativa|positiva|neutra — valida e devolve '' se ausente. */
function kdd_polaridade_req(): string
{
    if (!isset($_GET['polaridade']) || trim((string) $_GET['polaridade']) === '') {
        return '';
    }
    $v = strtolower(trim((string) $_GET['polaridade']));
    if (!in_array($v, ['negativa', 'positiva', 'neutra'], true)) {
        json_error('polaridade inválida: use negativa, positiva ou neutra', 400);
    }
    return $v;
}
