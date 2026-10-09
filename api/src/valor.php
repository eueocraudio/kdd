<?php
declare(strict_types=1);

/**
 * VALOR do conhecimento (0–100) de uma proposição e ESTEIO de um conceito.
 * Spec: docs/valor-conhecimento.md §3. Tudo é CÁLCULO EM LEITURA — nada persistido:
 * o grafo é a verdade; valor/esteio são derivados dele.
 *
 *   valor = 100 × (0,45·estrutura + 0,30·reforço + 0,25·esteio)
 *   estrutura = média(peso tipo origem, peso relação, peso tipo destino)
 *   reforço   = n/(n+1), n = fontes aprovadas (certeza da view)
 *   esteio    = 0,7·esteio(origem) + 0,3·esteio(destino);  esteio(c) = ln(1+grau)/ln(1+grau_max)
 */

const KDD_TIPOS_CONCEITO = ['entidade', 'classe', 'processo', 'atributo', 'outro'];

/** Peso do tipo do conceito quando ORIGEM (decisão II: entidade/persona/organização vale mais). */
const KDD_PESO_TIPO_ORIGEM  = ['entidade' => 1.0, 'classe' => 0.7, 'processo' => 0.6, 'atributo' => 0.4, 'outro' => 0.5];
/** Peso do tipo do conceito quando DESTINO (decisão II: classificação vale mais). */
const KDD_PESO_TIPO_DESTINO = ['classe' => 1.0, 'entidade' => 0.8, 'processo' => 0.7, 'atributo' => 0.6, 'outro' => 0.5];
const KDD_PESO_TIPO_DESCONHECIDO = 0.5;

/**
 * Relações TAXONÔMICAS / de PERTENCIMENTO — os verbos PERTENCER, SER, ESTAR e INCLUIR e seus
 * parentes (conter, compor, fazer parte de). Decisão do idealizador (2026-10-09): essas
 * ligações **REFORÇAM** o vínculo em vez de enfraquecê-lo.
 *
 * Por quê: num mapa de Novak a HIERARQUIA é o esqueleto — uma ligação dessas faz trabalho
 * duplo, afirma um fato E posiciona o conceito na hierarquia, o que torna o mapa navegável.
 * Além disso são exatamente elas que entregam a "classificação" da decisão II (entidade +
 * verbo + classificação = o mais alto). Pesam como verbo forte (1,0) e ainda ganham o bônus
 * taxonômico abaixo.
 *
 * ⚠️ Não confundir com as VAGAS: "relaciona-se com" também é estrutural, mas não classifica
 * nada — essa continua fraca.
 *
 * Lista curável; compare sempre após kdd_normalizar_relacao() (minúsculas, sem acento,
 * '_' vira espaço). Inclui as flexões porque a IA emite o verbo conjugado, não o infinitivo.
 */
const KDD_RELACOES_TAXONOMICAS = [
    // os quatro INFINITIVOS como o idealizador os nomeou (caso a IA emita a forma crua)
    'pertencer', 'ser', 'estar', 'incluir', 'conter', 'compor', 'pertencer a',
    // PERTENCER
    'pertence', 'pertence a', 'pertence ao', 'pertencem a', 'pertencia a', 'membro de',
    'integra', 'subconjunto de',
    // SER
    'e', 'e um', 'e uma', 'e o', 'e a', 'sao', 'e um tipo de', 'e tipo de', 'tipo de',
    'e uma forma de', 'e um caso de', 'e instancia de', 'e exemplo de', 'exemplo de',
    'e classificado como', 'e classificada como', 'classifica-se como', 'categoria de',
    // ESTAR
    'esta', 'esta em', 'esta no', 'esta na', 'estao em', 'encontra-se em', 'localiza-se em',
    'situa-se em', 'esta contido em', 'esta incluido em',
    // INCLUIR / conter / compor (o mesmo eixo, no sentido inverso)
    'inclui', 'incluem', 'abrange', 'engloba', 'compreende', 'contem', 'parte de',
    'e parte de', 'faz parte de', 'compoe', 'compoe-se de', 'composto por', 'composta por',
];

/**
 * Relações VAGAS: estruturais mas sem conteúdo — não dizem nem o que o conceito É nem a que
 * ele PERTENCE. Continuam valendo pouco. Lista curável.
 *
 * 'tem'/'possui' ficam aqui por decisão prática: às vezes são meronímia ("carro tem rodas",
 * que seria taxonômico), às vezes atributo ("tem cor azul"). Na dúvida, não reforça.
 */
const KDD_RELACOES_VAGAS = [
    'tem', 'possui', 'participa', 'participa de', 'relaciona-se com', 'relacionado a',
    'relacionada a', 'relacionado com', 'associado a', 'associada a', 'ligado a', 'ligada a',
    'refere-se a', 'sobre', 'para',
];

const KDD_PESO_RELACAO_VERBAL      = 1.0;
const KDD_PESO_RELACAO_TAXONOMICA  = 1.0;   // pesa como verbo forte — e ganha o bônus abaixo
const KDD_PESO_RELACAO_VAGA        = 0.5;
const KDD_PESO_RELACAO_VAZIA       = 0.3;   // token curtíssimo ("de", "em"): quase não diz nada

/**
 * REFORÇO da ligação taxonômica: aplicado sobre o que FALTA para 100, nunca somado direto —
 * assim o valor jamais passa de 100 e o reforço é maior onde há folga.
 *   valor = base + BONUS × (1 − base)
 */
const KDD_BONUS_TAXONOMICO = 0.10;

const KDD_W_ESTRUTURA = 0.45;
const KDD_W_REFORCO   = 0.30;
const KDD_W_ESTEIO    = 0.25;

function kdd_normalizar_relacao(string $r): string
{
    $r = mb_strtolower(trim($r));
    $r = str_replace('_', ' ', $r);
    $r = strtr($r, [
        'á' => 'a', 'à' => 'a', 'ã' => 'a', 'â' => 'a', 'é' => 'e', 'ê' => 'e', 'í' => 'i',
        'ó' => 'o', 'õ' => 'o', 'ô' => 'o', 'ú' => 'u', 'ü' => 'u', 'ç' => 'c',
    ]);
    return trim((string) preg_replace('/\s+/', ' ', $r));
}

/**
 * Classe da relação: 'taxonomica' | 'verbal' | 'vaga' | 'vazia'.
 * As duas listas são checadas ANTES do corte por tamanho: senão 'é' (ser) e 'tem', ambas
 * curtas, nunca chegariam à lista e cairiam em 'vazia'.
 */
function kdd_classe_relacao(string $relacao): string
{
    $n = kdd_normalizar_relacao($relacao);
    if (in_array($n, KDD_RELACOES_TAXONOMICAS, true)) {
        return 'taxonomica';
    }
    if (in_array($n, KDD_RELACOES_VAGAS, true)) {
        return 'vaga';
    }
    if ($n === '' || mb_strlen($n) <= 3) {
        return 'vazia';
    }
    return 'verbal';
}

/** Peso da relação na componente 'estrutura', conforme a classe. */
function kdd_peso_relacao(string $relacao): float
{
    switch (kdd_classe_relacao($relacao)) {
        case 'taxonomica': return KDD_PESO_RELACAO_TAXONOMICA;
        case 'vaga':       return KDD_PESO_RELACAO_VAGA;
        case 'vazia':      return KDD_PESO_RELACAO_VAZIA;
        default:           return KDD_PESO_RELACAO_VERBAL;
    }
}

function kdd_peso_tipo(?string $tipo, string $lado): float
{
    $tabela = $lado === 'origem' ? KDD_PESO_TIPO_ORIGEM : KDD_PESO_TIPO_DESTINO;
    return $tipo !== null && isset($tabela[$tipo]) ? $tabela[$tipo] : KDD_PESO_TIPO_DESCONHECIDO;
}

/** Esteio de um conceito em [0,1]: escala log do grau em relação ao maior grau do armazém. */
function kdd_esteio(int $grau, int $grauMax): float
{
    if ($grau <= 0 || $grauMax <= 0) {
        return 0.0;
    }
    return min(1.0, log(1 + $grau) / log(1 + $grauMax));
}

/**
 * Maior grau (saída+entrada) DENTRO DE UM UNIVERSO, neste instante.
 *
 * ⚠️ Tem que ser por universo (docs/universos.md §3). Se fosse global, um universo novo e
 * pequeno teria todo o seu esteio esmagado pelo maior hub do maior universo, e o valor das
 * proposições dele despencaria sem nenhuma razão de domínio. É o ponto mais fácil de errar
 * nos universos paralelos.
 */
function kdd_grau_max(PDO $pdo, int $universoId): int
{
    static $cache = [];
    if (!array_key_exists($universoId, $cache)) {
        $s = $pdo->prepare(
            "SELECT COALESCE(MAX(g.grau_saida + g.grau_entrada), 0)
               FROM vw_grau_conceito g
               JOIN conceito c ON c.id = g.conceito_id
              WHERE c.universo_id = ?"
        );
        $s->execute([$universoId]);
        $cache[$universoId] = (int) $s->fetchColumn();
    }
    return $cache[$universoId];
}

/**
 * Valor 0–100 de uma proposição + detalhe das componentes (todas em [0,1]).
 */
function kdd_valor_proposicao(
    ?string $tipoOrigem, string $relacao, ?string $tipoDestino,
    int $fontesAprovadas, int $grauOrigem, int $grauDestino, int $grauMax,
    ?float $subjetividade = null
): array {
    $classe    = kdd_classe_relacao($relacao);
    $estrutura = (kdd_peso_tipo($tipoOrigem, 'origem') + kdd_peso_relacao($relacao) + kdd_peso_tipo($tipoDestino, 'destino')) / 3;
    $reforco   = $fontesAprovadas > 0 ? $fontesAprovadas / ($fontesAprovadas + 1) : 0.0;
    $esteio    = 0.7 * kdd_esteio($grauOrigem, $grauMax) + 0.3 * kdd_esteio($grauDestino, $grauMax);
    $base      = KDD_W_ESTRUTURA * $estrutura + KDD_W_REFORCO * $reforco + KDD_W_ESTEIO * $esteio;

    // Reforço da ligação hierárquica (pertencer/ser/estar/incluir) sobre a folga até 100.
    $bonus = $classe === 'taxonomica' ? KDD_BONUS_TAXONOMICO * (1 - $base) : 0.0;
    $valor = $base + $bonus;

    // ⚠️ DESCONTO DE SUBJETIVIDADE (docs/sentimento.md §4): juízo de valor vale menos como
    // conhecimento que fato. Multiplicativo e limitado: subjetividade 0 não muda nada,
    // subjetividade 1 tira 20%. Omissão (null) NÃO penaliza — base existente fica igual.
    //
    // A POLARIDADE deliberadamente NÃO entra aqui: um fato negativo vale tanto quanto um
    // positivo, e descontar o negativo injetaria viés otimista no armazém.
    $sub = $subjetividade !== null ? max(0.0, min(1.0, $subjetividade)) : 0.0;
    $desconto = KDD_DESCONTO_SUBJETIVIDADE * $sub;
    $valor = $valor * (1 - $desconto);

    return [
        'valor'         => (int) round(100 * $valor),
        'valor_detalhe' => [
            'estrutura'      => round($estrutura, 3),
            'reforco'        => round($reforco, 3),
            'esteio'         => round($esteio, 3),
            'relacao_classe' => $classe,
            'bonus_taxonomico' => round($bonus, 3),
            'desconto_subjetividade' => round($desconto, 3),
        ],
    ];
}

/**
 * tipo + grau + universo de um conjunto de conceitos:
 * id → ['tipo'=>?, 'grau'=>int, 'saida'=>, 'entrada'=>, 'fontes'=>, 'universo_id'=>].
 *
 * O `universo_id` vem junto porque o esteio é relativo ao universo DO CONCEITO — e uma
 * listagem pode cruzar universos (ex.: contrapartes).
 */
function kdd_info_conceitos(PDO $pdo, array $ids): array
{
    $ids = array_values(array_unique(array_map('intval', $ids)));
    if (!$ids) {
        return [];
    }
    $ph = implode(',', array_fill(0, count($ids), '?'));
    $s  = $pdo->prepare(
        "SELECT c.id, c.tipo, c.universo_id, g.grau_saida, g.grau_entrada, g.fontes
           FROM conceito c JOIN vw_grau_conceito g ON g.conceito_id = c.id
          WHERE c.id IN ($ph)"
    );
    $s->execute($ids);
    $out = [];
    foreach ($s->fetchAll() as $r) {
        $out[(int) $r['id']] = [
            'tipo'        => $r['tipo'],
            'saida'       => (int) $r['grau_saida'],
            'entrada'     => (int) $r['grau_entrada'],
            'fontes'      => (int) $r['fontes'],
            'grau'        => (int) $r['grau_saida'] + (int) $r['grau_entrada'],
            'universo_id' => (int) $r['universo_id'],
        ];
    }
    return $out;
}

/**
 * Acrescenta valor/valor_detalhe a proposições já montadas como arrays com
 * 'relacao', 'fontes_aprovadas' e os ids em 'origem'['id'] / 'destino'['id']
 * (ou nas chaves internas '_origem_id' / '_destino_id', removidas na saída).
 */
function kdd_enriquecer_proposicoes(PDO $pdo, array $props): array
{
    $ids = [];
    foreach ($props as $p) {
        $ids[] = $p['_origem_id']  ?? $p['origem']['id'];
        $ids[] = $p['_destino_id'] ?? $p['destino']['id'];
    }
    $info = kdd_info_conceitos($pdo, $ids);
    // Sentimento (medido pelo bot, agregado pela view) — a subjetividade desconta o valor.
    $sent = kdd_sentimento_proposicoes($pdo, array_map(
        static fn(array $p): int => (int) ($p['proposicao_id'] ?? $p['id'] ?? 0), $props
    ));

    foreach ($props as &$p) {
        $o = (int) ($p['_origem_id']  ?? $p['origem']['id']);
        $d = (int) ($p['_destino_id'] ?? $p['destino']['id']);
        $io = $info[$o] ?? ['tipo' => null, 'grau' => 0, 'universo_id' => 1];
        $id = $info[$d] ?? ['tipo' => null, 'grau' => 0, 'universo_id' => 1];
        // Proposição nunca cruza universo (invariante da escrita), então o universo da
        // origem É o da proposição — e o grau_max é o daquele universo.
        $grauMax = kdd_grau_max($pdo, (int) ($io['universo_id'] ?? 1));
        $pid = (int) ($p['proposicao_id'] ?? $p['id'] ?? 0);
        $s   = $sent[$pid] ?? null;
        $p['sentimento'] = $s ?? [
            'polaridade' => null, 'subjetividade' => null, 'fontes_medidas' => 0,
            'discordancia' => 0.0, 'rotulo' => 'nao_medida', 'origem' => 'nao_medido',
        ];
        $p += kdd_valor_proposicao(
            $io['tipo'], (string) $p['relacao'], $id['tipo'],
            (int) ($p['fontes_aprovadas'] ?? 0), $io['grau'], $id['grau'], $grauMax,
            $s['subjetividade'] ?? null
        );
        unset($p['_origem_id'], $p['_destino_id']);
    }
    unset($p);
    return $props;
}

/** Acrescenta tipo, grau {saida, entrada, fontes} e esteio (0–100) a conceitos montados com 'id'. */
function kdd_enriquecer_conceitos(PDO $pdo, array $conceitos): array
{
    $info = kdd_info_conceitos($pdo, array_column($conceitos, 'id'));
    foreach ($conceitos as &$c) {
        $i = $info[(int) $c['id']]
            ?? ['tipo' => null, 'saida' => 0, 'entrada' => 0, 'fontes' => 0, 'grau' => 0, 'universo_id' => 1];
        // esteio é relativo ao universo DO CONCEITO (a listagem pode cruzar universos).
        $grauMax = kdd_grau_max($pdo, (int) ($i['universo_id'] ?? 1));
        $c['tipo']   = $i['tipo'];
        $c['grau']   = ['saida' => $i['saida'], 'entrada' => $i['entrada'], 'fontes' => $i['fontes']];
        $c['esteio'] = (int) round(100 * kdd_esteio($i['grau'], $grauMax));
    }
    unset($c);
    return $conceitos;
}

/** Valida/normaliza um tipo vindo do cliente; null se inválido ou vazio. */
function kdd_tipo_valido($tipo): ?string
{
    $t = mb_strtolower(trim((string) $tipo));
    return in_array($t, KDD_TIPOS_CONCEITO, true) ? $t : null;
}
