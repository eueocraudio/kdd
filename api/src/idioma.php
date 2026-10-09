<?php
declare(strict_types=1);

/**
 * IDIOMA e PAÍS (docs/idioma-pais.md).
 *
 * Dois problemas de natureza diferente:
 *   · IDIOMA é superfície → vive no RÓTULO. Porta/Door = UM conceito, dois rótulos.
 *   · PAÍS pode mudar o SENTIDO → vive na IDENTIDADE (universo, pais, sentido).
 *
 * ⚠️ As duas semânticas de filtro NÃO são iguais:
 *   · universo → igualdade estrita (é outro plano)
 *   · país     → INCLUSIVO: pais IN ('', <escolhido>) — universal MAIS o do país pedido.
 *     País marca jurisdição DENTRO de um plano; não cria plano.
 */

const KDD_IDIOMA_PADRAO = 'pt-BR';

/** Valida uma tag de idioma estilo BCP-47 (pt, pt-BR, en-US, es-AR). '' se inválida. */
function kdd_idioma_valido($tag): string
{
    $t = trim((string) $tag);
    if ($t === '' || strlen($t) > 16) {
        return '';
    }
    // 2–3 letras minúsculas, opcionalmente -SUBTAG alfanumérica. Sem espaço, quote ou acento:
    // é o que torna seguro interpolar a tag no ORDER BY (ver kdd_sql_rotulo).
    if (!preg_match('/^[a-z]{2,3}(-[A-Za-z0-9]{2,8})?$/', $t)) {
        return '';
    }
    return $t;
}

/** Valida um código de país ISO 3166-1 alfa-2. '' = universal (e também o inválido). */
function kdd_pais_valido($codigo): string
{
    $c = strtoupper(trim((string) $codigo));
    return preg_match('/^[A-Z]{2}$/', $c) ? $c : '';
}

/**
 * Idioma pedido na requisição (`?idioma=`), já validado. '' = sem preferência.
 * Tag malformada é recusada em vez de ignorada em silêncio.
 */
function kdd_idioma_req(): string
{
    if (!isset($_GET['idioma']) || trim((string) $_GET['idioma']) === '') {
        return '';
    }
    $t = kdd_idioma_valido($_GET['idioma']);
    if ($t === '') {
        json_error('idioma inválido: use uma tag como pt-BR, pt, en ou es-AR', 400);
    }
    return $t;
}

/**
 * País pedido na requisição (`?pais=`), já validado. '' = sem filtro (traz TUDO:
 * universal e de todos os países — é o comportamento de antes desta camada).
 */
function kdd_pais_req(): string
{
    if (!isset($_GET['pais']) || trim((string) $_GET['pais']) === '') {
        return '';
    }
    $c = kdd_pais_valido($_GET['pais']);
    if ($c === '') {
        json_error('pais inválido: use o código ISO de 2 letras, como BR ou PT', 400);
    }
    return $c;
}

/**
 * Trecho SQL `pais IN ('', 'XX')` para o filtro INCLUSIVO, ou '' quando não há filtro.
 * `$coluna` é um nome de coluna do próprio código (ex.: 'c.pais'), nunca entrada do usuário.
 * O código do país já passou por kdd_pais_valido() (exatamente 2 letras A–Z).
 */
function kdd_sql_filtro_pais(string $coluna, string $pais): string
{
    if ($pais === '') {
        return '';
    }
    return "$coluna IN ('', '$pais')";
}

/**
 * Subconsulta que escolhe UM rótulo do conceito, com FALLBACK de idioma.
 *
 * Ordem de preferência: idioma pedido → idioma-base do universo do conceito → principal →
 * menor id. Nunca devolve vazio só porque falta a tradução: um mapa meio traduzido continua
 * navegável (docs/idioma-pais.md §3).
 *
 * ⚠️ A tag de idioma é INTERPOLADA, não parametrizada — de propósito: esta subconsulta é
 * usada em ~19 queries com listas de parâmetros diferentes, e enfiar um placeholder em cada
 * uma na posição certa seria frágil. É seguro porque kdd_idioma_valido() só deixa passar
 * [a-z]{2,3}(-[A-Za-z0-9]{2,8})? — sem quote, espaço ou metacaractere possível.
 *
 * @param string $colConceito coluna com o id do conceito (ex.: 'c.id', 'p.conceito_origem')
 * @param string $idioma      tag JÁ validada, ou '' para sem preferência
 */
function kdd_sql_rotulo(string $colConceito, string $idioma): string
{
    if ($idioma === '') {
        return "(SELECT r.texto FROM rotulo r WHERE r.conceito_id = $colConceito
                  ORDER BY r.principal DESC, r.id LIMIT 1)";
    }
    $i = kdd_idioma_valido($idioma);
    if ($i === '') {
        // defesa em profundidade: chamada interna com tag suja cai no caso sem preferência
        return kdd_sql_rotulo($colConceito, '');
    }
    // idioma exato > mesma língua com outra região ('pt-PT' quando se pediu 'pt-BR') >
    // idioma-base do universo > principal > menor id
    $base = substr($i, 0, 2);
    return "(SELECT r.texto FROM rotulo r
               JOIN conceito rc ON rc.id = r.conceito_id
               JOIN universo ru ON ru.id = rc.universo_id
              WHERE r.conceito_id = $colConceito
              ORDER BY (r.idioma = '$i') DESC,
                       (r.idioma LIKE '$base%') DESC,
                       (r.idioma = ru.idioma) DESC,
                       r.principal DESC, r.id
              LIMIT 1)";
}
