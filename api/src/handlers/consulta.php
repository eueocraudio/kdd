<?php
declare(strict_types=1);

/**
 * Endpoints de CONSULTA do armazém (somente leitura).
 * Pensados para humanos E máquinas navegarem a base com os scores de certeza.
 *
 * Certeza: exposta como `fontes_aprovadas` (nº de fontes APROVADAS que sustentam a
 * proposição — o sinal linear definido na especificação, calculado na view
 * vw_certeza_proposicao). A normalização para [0,1] fica deliberadamente de fora
 * por enquanto (decisão da fórmula adiada — ver plano §Certeza).
 */

/* ───────────────────────── Áreas ───────────────────────── */

/**
 * GET /areas — árvore hierárquica (parent_id auto-referenciado).
 * Monta a árvore em PHP a partir da lista plana.
 */
function areas_arvore(): void
{
    $pdo = kdd_db();
    $uid = kdd_universo_req($pdo);
    $s = $pdo->prepare("SELECT id, nome, parent_id FROM area WHERE universo_id = ? ORDER BY nome");
    $s->execute([$uid]);
    $rows = $s->fetchAll();

    $por_id = [];
    foreach ($rows as $r) {
        $por_id[(int) $r['id']] = [
            'id'     => (int) $r['id'],
            'nome'   => $r['nome'],
            'filhos' => [],
        ];
    }

    $raiz = [];
    foreach ($rows as $r) {
        $id  = (int) $r['id'];
        $pai = $r['parent_id'] !== null ? (int) $r['parent_id'] : null;
        if ($pai !== null && isset($por_id[$pai])) {
            $por_id[$pai]['filhos'][] = &$por_id[$id];
        } else {
            $raiz[] = &$por_id[$id];
        }
    }

    json_out(['universo' => kdd_universo_resumo($pdo, $uid), 'areas' => $raiz]);
}

/* ─────────────────────── Conceitos ──────────────────────── */

/**
 * GET /conceitos — lista conceitos com rótulos e áreas.
 * Filtros opcionais: ?q=<texto> (busca por rótulo), ?area=<id>.
 */
function conceitos_listar(): void
{
    $pdo    = kdd_db();
    $uid    = kdd_universo_req($pdo);
    $idioma = kdd_idioma_req();
    $pais   = kdd_pais_req();
    $q      = trim((string) ($_GET['q']    ?? ''));
    // ?area aceita id único ou lista CSV (?area=1,2,3) — semântica de UNIÃO
    // (conceitos em QUALQUER das áreas). Retrocompatível com ?area=1.
    $areaIds = [];
    if (isset($_GET['area']) && $_GET['area'] !== '') {
        foreach (explode(',', (string) $_GET['area']) as $a) {
            $a = (int) trim($a);
            if ($a > 0) {
                $areaIds[] = $a;
            }
        }
        $areaIds = array_values(array_unique($areaIds));
    }
    // ?fonte=<id> — "lente de contexto": só conceitos daquela fonte (proveniência).
    $fonteId = isset($_GET['fonte']) && $_GET['fonte'] !== '' ? (int) $_GET['fonte'] : null;

    // Universo é o 1º filtro: nada de outro universo vaza daqui (docs/universos.md §8.3).
    $where  = ['c.universo_id = ?'];
    $params = [$uid];

    // País é filtro INCLUSIVO (docs/idioma-pais.md §4): universal MAIS o do país pedido.
    // Semântica diferente do universo de propósito — país marca jurisdição DENTRO do plano.
    if ($filtroPais = kdd_sql_filtro_pais('c.pais', $pais)) {
        $where[] = $filtroPais;
    }

    if ($q !== '') {
        $where[]  = "EXISTS (SELECT 1 FROM rotulo rq WHERE rq.conceito_id = c.id AND rq.texto LIKE ?)";
        $params[] = '%' . $q . '%';
    }
    if ($areaIds) {
        $ph = implode(',', array_fill(0, count($areaIds), '?'));
        $where[] = "EXISTS (SELECT 1 FROM conceito_area cq WHERE cq.conceito_id = c.id AND cq.area_id IN ($ph))";
        foreach ($areaIds as $a) {
            $params[] = $a;
        }
    }
    if ($fonteId !== null) {
        $where[]  = "EXISTS (SELECT 1 FROM conceito_fonte cf WHERE cf.conceito_id = c.id AND cf.fonte_id = ?)";
        $params[] = $fonteId;
    }

    // 'rotulo' = o escolhido pelo idioma (com fallback); 'rotulos' = todos, como antes.
    $sql = "SELECT c.id, c.sentido, c.desabilitado, c.pais,
                   " . kdd_sql_rotulo('c.id', $idioma) . " AS rotulo,
                   GROUP_CONCAT(DISTINCT r.texto ORDER BY r.principal DESC, r.texto SEPARATOR ', ') AS rotulos,
                   GROUP_CONCAT(DISTINCT a.nome  ORDER BY a.nome SEPARATOR ', ')                    AS areas
              FROM conceito c
              LEFT JOIN rotulo r        ON r.conceito_id = c.id
              LEFT JOIN conceito_area ca ON ca.conceito_id = c.id
              LEFT JOIN area a          ON a.id = ca.area_id";
    if ($where) {
        $sql .= " WHERE " . implode(' AND ', $where);
    }
    $sql .= " GROUP BY c.id, c.sentido, c.desabilitado, c.pais ORDER BY c.id";

    $stmt = $pdo->prepare($sql);
    $stmt->execute($params);

    $conceitos = array_map(static function (array $row): array {
        $row['id']           = (int) $row['id'];
        $row['desabilitado'] = (int) $row['desabilitado'];
        return $row;
    }, $stmt->fetchAll());

    // tipo + grau + esteio (docs/valor-conhecimento.md §3)
    $conceitos = kdd_enriquecer_conceitos($pdo, $conceitos);

    json_out(['universo' => kdd_universo_resumo($pdo, $uid),
              'idioma' => $idioma ?: null, 'pais' => $pais ?: null,
              'conceitos' => $conceitos]);
}

/**
 * GET /conceitos/{id} — detalhe: rótulos, áreas, fontes que o introduziram,
 * e proposições onde participa (como origem e como destino) com a certeza.
 */
function conceitos_obter(int $id): void
{
    $pdo  = kdd_db();
    $idioma = kdd_idioma_req();
    $stmt = $pdo->prepare(
        "SELECT id, sentido, desabilitado, criado_em, universo_id, pais FROM conceito WHERE id = ?"
    );
    $stmt->execute([$id]);
    $conceito = $stmt->fetch();
    if (!$conceito) {
        json_error('Conceito não encontrado', 404);
    }
    // O id é global, então não se filtra por universo aqui — mas a resposta DIZ qual é.
    $conceito['universo'] = kdd_universo_resumo($pdo, (int) $conceito['universo_id']);
    unset($conceito['universo_id']);
    $conceito['id']           = (int) $conceito['id'];
    $conceito['desabilitado'] = (int) $conceito['desabilitado'];

    // tipo + grau + esteio do próprio conceito (docs/valor-conhecimento.md §3)
    $conceito = kdd_enriquecer_conceitos($pdo, [$conceito])[0];

    // Rótulos: TODOS, cada um com o seu idioma — é assim que o cliente mostra as traduções.
    $s = $pdo->prepare(
        "SELECT id, texto, idioma, principal FROM rotulo WHERE conceito_id = ?
          ORDER BY principal DESC, idioma, texto"
    );
    $s->execute([$id]);
    $conceito['rotulos'] = array_map(static function (array $r): array {
        return ['id' => (int) $r['id'], 'texto' => $r['texto'], 'idioma' => $r['idioma'],
                'principal' => (bool) $r['principal']];
    }, $s->fetchAll());
    $conceito['idiomas'] = array_values(array_unique(array_column($conceito['rotulos'], 'idioma')));

    // Áreas
    $s = $pdo->prepare(
        "SELECT a.id, a.nome FROM area a
           JOIN conceito_area ca ON ca.area_id = a.id
          WHERE ca.conceito_id = ? ORDER BY a.nome"
    );
    $s->execute([$id]);
    $conceito['areas'] = array_map(static function (array $a): array {
        return ['id' => (int) $a['id'], 'nome' => $a['nome']];
    }, $s->fetchAll());

    // Fontes que introduziram/usaram o conceito
    $s = $pdo->prepare(
        "SELECT f.id, f.titulo, f.status_aprovacao FROM fonte f
           JOIN conceito_fonte cf ON cf.fonte_id = f.id
          WHERE cf.conceito_id = ? ORDER BY f.id"
    );
    $s->execute([$id]);
    $conceito['fontes'] = array_map(static function (array $f): array {
        return ['id' => (int) $f['id'], 'titulo' => $f['titulo'], 'status_aprovacao' => $f['status_aprovacao']];
    }, $s->fetchAll());

    // Proposições onde é ORIGEM
    $conceito['proposicoes_origem'] = kdd_proposicoes_do_conceito($pdo, $id, 'origem', $idioma);
    // Proposições onde é DESTINO
    $conceito['proposicoes_destino'] = kdd_proposicoes_do_conceito($pdo, $id, 'destino', $idioma);

    // AMEAÇAS x PROTEÇÕES: as proposições que CHEGAM ao conceito, separadas pela polaridade.
    // É a leitura que motivou a camada de sentimento (docs/sentimento.md §1): "o que ameaça
    // este conceito?" e "o que o protege?".
    $conceito['ameacas']   = [];
    $conceito['protecoes'] = [];
    foreach ($conceito['proposicoes_destino'] as $p) {
        $rotulo = $p['sentimento']['rotulo'] ?? 'nao_medida';
        if ($rotulo === 'negativa') {
            $conceito['ameacas'][] = $p;
        } elseif ($rotulo === 'positiva') {
            $conceito['protecoes'][] = $p;
        }
    }

    // Conceitos semanticamente semelhantes (camada vetorial — §6 da spec; vazio sem --vetorizar)
    $conceito['similares'] = kdd_similares_do_conceito($pdo, $id, 10, $idioma);

    json_out(['conceito' => $conceito]);
}

/**
 * Proposições em que o conceito participa, com o rótulo da "outra ponta" e a certeza.
 * $lado = 'origem' → lista as que saem do conceito; 'destino' → as que chegam nele.
 */
function kdd_proposicoes_do_conceito(PDO $pdo, int $conceitoId, string $lado,
                                     string $idioma = ''): array
{
    if ($lado === 'origem') {
        $col_self  = 'conceito_origem';
        $col_outro = 'conceito_destino';
        $chave     = 'destino';
    } else {
        $col_self  = 'conceito_destino';
        $col_outro = 'conceito_origem';
        $chave     = 'origem';
    }

    $sql = "SELECT p.id, p.relacao, p.pais, p.$col_self AS self_id, p.$col_outro AS outro_id,
                   " . kdd_sql_rotulo("p.$col_outro", $idioma) . " AS outro_rotulo,
                   v.fontes_aprovadas,
                   EXISTS (SELECT 1 FROM conceito cx
                            WHERE cx.id IN (p.conceito_origem, p.conceito_destino)
                              AND cx.desabilitado = 1) AS desabilitada
              FROM proposicao p
              JOIN vw_certeza_proposicao v ON v.proposicao_id = p.id
             WHERE p.$col_self = ?
             ORDER BY v.fontes_aprovadas DESC, p.id";
    $s = $pdo->prepare($sql);
    $s->execute([$conceitoId]);

    $props = array_map(static function (array $r) use ($chave, $lado): array {
        $item = [
            'proposicao_id'    => (int) $r['id'],
            'relacao'          => $r['relacao'],
            'pais'             => $r['pais'],
            $chave             => ['id' => (int) $r['outro_id'], 'rotulo' => $r['outro_rotulo']],
            'fontes_aprovadas' => (int) $r['fontes_aprovadas'],
            'desabilitada'     => (int) $r['desabilitada'],
        ];
        // ids explícitos para o cálculo do valor (removidos na saída)
        $item['_origem_id']  = $lado === 'origem' ? (int) $r['self_id']  : (int) $r['outro_id'];
        $item['_destino_id'] = $lado === 'origem' ? (int) $r['outro_id'] : (int) $r['self_id'];
        return $item;
    }, $s->fetchAll());

    // valor 0–100 por proposição (docs/valor-conhecimento.md §3)
    $props = kdd_enriquecer_proposicoes($pdo, $props);
    usort($props, static fn(array $a, array $b): int => $b['valor'] <=> $a['valor']);
    return $props;
}

/* ────────────────────── Proposições ─────────────────────── */

/**
 * GET /proposicoes — lista proposições com certeza (da view).
 * Filtro opcional ?conceito=<id> (origem OU destino).
 */
function proposicoes_listar(): void
{
    $pdo       = kdd_db();
    $uid       = kdd_universo_req($pdo);
    $idioma    = kdd_idioma_req();
    $pais      = kdd_pais_req();
    $polar     = kdd_polaridade_req();
    $conceito  = isset($_GET['conceito']) && $_GET['conceito'] !== '' ? (int) $_GET['conceito'] : null;

    $sql = "SELECT p.id, p.relacao, p.pais,
                   p.conceito_origem,
                   " . kdd_sql_rotulo('p.conceito_origem', $idioma) . " AS origem_rotulo,
                   p.conceito_destino,
                   " . kdd_sql_rotulo('p.conceito_destino', $idioma) . " AS destino_rotulo,
                   v.fontes_aprovadas,
                   EXISTS (SELECT 1 FROM conceito cx
                            WHERE cx.id IN (p.conceito_origem, p.conceito_destino)
                              AND cx.desabilitado = 1) AS desabilitada
              FROM proposicao p
              JOIN vw_certeza_proposicao v ON v.proposicao_id = p.id
              JOIN conceito co ON co.id = p.conceito_origem";
    // A proposição pertence ao universo dos seus conceitos (nunca cruza), então filtrar
    // pela origem basta.
    $sql   .= " WHERE co.universo_id = ?";
    $params = [$uid];
    // País INCLUSIVO: a mesma tripla pode valer num país e não noutro.
    if ($filtroPais = kdd_sql_filtro_pais('p.pais', $pais)) {
        $sql .= " AND $filtroPais";
    }
    if ($conceito !== null) {
        $sql     .= " AND (p.conceito_origem = ? OR p.conceito_destino = ?)";
        $params[] = $conceito;
        $params[] = $conceito;
    }
    $sql .= " ORDER BY v.fontes_aprovadas DESC, p.id";

    $stmt = $pdo->prepare($sql);
    $stmt->execute($params);

    $proposicoes = array_map(static function (array $r): array {
        return [
            'id'               => (int) $r['id'],
            'relacao'          => $r['relacao'],
            'pais'             => $r['pais'],
            'origem'           => ['id' => (int) $r['conceito_origem'],  'rotulo' => $r['origem_rotulo']],
            'destino'          => ['id' => (int) $r['conceito_destino'], 'rotulo' => $r['destino_rotulo']],
            'fontes_aprovadas' => (int) $r['fontes_aprovadas'],
            'desabilitada'     => (int) $r['desabilitada'],
        ];
    }, $stmt->fetchAll());

    // valor 0–100 + sentimento, e ordenação por valor (docs/valor-conhecimento.md §3)
    $proposicoes = kdd_enriquecer_proposicoes($pdo, $proposicoes);

    // Filtro por polaridade DEPOIS do enriquecimento: o sentimento é agregado em PHP a
    // partir da view, não é coluna da proposição.
    if ($polar !== '') {
        $proposicoes = array_values(array_filter(
            $proposicoes,
            static fn(array $p): bool => ($p['sentimento']['rotulo'] ?? 'nao_medida') === $polar
        ));
    }
    usort($proposicoes, static fn(array $a, array $b): int => $b['valor'] <=> $a['valor']);

    json_out(['universo' => kdd_universo_resumo($pdo, $uid),
              'idioma' => $idioma ?: null, 'pais' => $pais ?: null,
              'polaridade' => $polar ?: null,
              'proposicoes' => $proposicoes]);
}

/**
 * GET /fontes/{id}/mapa — conceitos e proposições de uma fonte (documento),
 * para desenhar o mapa conceitual inteiro daquele PDF. Os conceitos saem de
 * conceito_fonte; as proposições, das referências da própria fonte (com certeza).
 */
function fonte_mapa(int $id): void
{
    $pdo    = kdd_db();
    $idioma = kdd_idioma_req();
    $s = $pdo->prepare("SELECT id, titulo, universo_id FROM fonte WHERE id = ?");
    $s->execute([$id]);
    $fonte = $s->fetch();
    if (!$fonte) {
        json_error('Fonte não encontrada', 404);
    }

    $s = $pdo->prepare(
        "SELECT c.id, c.sentido, c.desabilitado, c.pais,
                " . kdd_sql_rotulo('c.id', $idioma) . " AS rotulo,
                GROUP_CONCAT(DISTINCT a.nome ORDER BY a.nome SEPARATOR ', ') AS areas
           FROM conceito_fonte cf
           JOIN conceito c          ON c.id = cf.conceito_id
           LEFT JOIN conceito_area ca ON ca.conceito_id = c.id
           LEFT JOIN area a         ON a.id = ca.area_id
          WHERE cf.fonte_id = ?
          GROUP BY c.id, c.sentido, c.desabilitado ORDER BY c.id"
    );
    $s->execute([$id]);
    $conceitos = kdd_enriquecer_conceitos($pdo, array_map(static function (array $r): array {
        return ['id' => (int) $r['id'], 'rotulo' => $r['rotulo'], 'sentido' => $r['sentido'],
                'areas' => $r['areas'], 'pais' => $r['pais'],
                'desabilitado' => (int) $r['desabilitado']];
    }, $s->fetchAll()));

    $s = $pdo->prepare(
        "SELECT p.id, p.relacao, p.pais,
                p.conceito_origem  AS origem_id,
                " . kdd_sql_rotulo('p.conceito_origem', $idioma) . " AS origem_rotulo,
                p.conceito_destino AS destino_id,
                " . kdd_sql_rotulo('p.conceito_destino', $idioma) . " AS destino_rotulo,
                v.fontes_aprovadas,
                EXISTS (SELECT 1 FROM conceito cx
                         WHERE cx.id IN (p.conceito_origem, p.conceito_destino)
                           AND cx.desabilitado = 1) AS desabilitada
           FROM referencia rf
           JOIN proposicao p ON p.id = rf.proposicao_id
           JOIN vw_certeza_proposicao v ON v.proposicao_id = p.id
          WHERE rf.fonte_id = ?
          ORDER BY p.id"
    );
    $s->execute([$id]);
    $proposicoes = kdd_enriquecer_proposicoes($pdo, array_map(static function (array $r): array {
        return [
            'id'               => (int) $r['id'],
            'relacao'          => $r['relacao'],
            'pais'             => $r['pais'],
            'origem'           => ['id' => (int) $r['origem_id'],  'rotulo' => $r['origem_rotulo']],
            'destino'          => ['id' => (int) $r['destino_id'], 'rotulo' => $r['destino_rotulo']],
            'fontes_aprovadas' => (int) $r['fontes_aprovadas'],
            'desabilitada'     => (int) $r['desabilitada'],
        ];
    }, $s->fetchAll()));

    json_out(['fonte' => ['id' => (int) $fonte['id'], 'titulo' => $fonte['titulo'],
                          'universo' => kdd_universo_resumo($pdo, (int) $fonte['universo_id'])],
              'conceitos' => $conceitos, 'proposicoes' => $proposicoes]);
}

/* ─────────────────────── Constelação ─────────────────────── */

/**
 * GET /constelacao — visão macro: áreas (com contagem de conceitos),
 * pontes interdisciplinares (proposições cujos conceitos vivem em áreas distintas)
 * e homônimos (rótulos compartilhados por conceitos diferentes).
 */
function constelacao(): void
{
    $pdo    = kdd_db();
    $uid    = kdd_universo_req($pdo);
    $idioma = kdd_idioma_req();

    // Áreas com contagem de conceitos
    $s = $pdo->prepare(
        "SELECT a.id, a.nome, COUNT(DISTINCT ca.conceito_id) AS conceitos
           FROM area a
           LEFT JOIN conceito_area ca ON ca.area_id = a.id
          WHERE a.universo_id = ?
          GROUP BY a.id, a.nome ORDER BY a.nome"
    );
    $s->execute([$uid]);
    $areas = $s->fetchAll();
    $areas = array_map(static function (array $a): array {
        return ['id' => (int) $a['id'], 'nome' => $a['nome'], 'conceitos' => (int) $a['conceitos']];
    }, $areas);

    // Pontes interdisciplinares: proposições cuja origem e destino não compartilham área.
    // Dentro do universo — ponte ENTRE universos não é proposição, é contraparte (§5).
    $s = $pdo->prepare(
        "SELECT p.id, p.relacao, p.pais,
                p.conceito_origem  AS origem_id,
                " . kdd_sql_rotulo('p.conceito_origem', $idioma) . " AS origem_rotulo,
                p.conceito_destino AS destino_id,
                " . kdd_sql_rotulo('p.conceito_destino', $idioma) . " AS destino_rotulo
           FROM proposicao p
           JOIN conceito co ON co.id = p.conceito_origem
          WHERE co.universo_id = ?
            AND NOT EXISTS (
                  SELECT 1 FROM conceito_area cao
                    JOIN conceito_area cad ON cad.area_id = cao.area_id
                   WHERE cao.conceito_id = p.conceito_origem
                     AND cad.conceito_id = p.conceito_destino)
          ORDER BY p.id"
    );
    $s->execute([$uid]);
    $pontes = $s->fetchAll();
    $pontes = array_map(static function (array $r): array {
        return [
            'proposicao_id' => (int) $r['id'],
            'relacao'       => $r['relacao'],
            'pais'          => $r['pais'],
            'origem'        => ['id' => (int) $r['origem_id'],  'rotulo' => $r['origem_rotulo']],
            'destino'       => ['id' => (int) $r['destino_id'], 'rotulo' => $r['destino_rotulo']],
        ];
    }, $pontes);

    // Homônimos: mesmo texto de rótulo apontando para conceitos (sentidos) diferentes.
    // Dentro do universo: o mesmo rótulo em OUTRO universo não é homônimo, é contraparte.
    $s = $pdo->prepare(
        "SELECT r.texto, COUNT(DISTINCT r.conceito_id) AS sentidos,
                GROUP_CONCAT(DISTINCT r.conceito_id ORDER BY r.conceito_id SEPARATOR ',') AS conceito_ids
           FROM rotulo r
           JOIN conceito c ON c.id = r.conceito_id
          WHERE c.universo_id = ?
          GROUP BY r.texto
         HAVING COUNT(DISTINCT r.conceito_id) > 1
          ORDER BY sentidos DESC, r.texto"
    );
    $s->execute([$uid]);
    $homonimos = $s->fetchAll();
    $homonimos = array_map(static function (array $h): array {
        return [
            'rotulo'       => $h['texto'],
            'sentidos'     => (int) $h['sentidos'],
            'conceito_ids' => array_map('intval', explode(',', $h['conceito_ids'])),
        ];
    }, $homonimos);

    json_out([
        'universo'  => kdd_universo_resumo($pdo, $uid),
        'areas'     => $areas,
        'pontes'    => $pontes,
        'homonimos' => $homonimos,
    ]);
}

/* ───────────────────────── Esteios ───────────────────────── */

/**
 * GET /esteios?limite=20 — os conceitos-pilar do armazém: os de maior GRAU (nº de relações
 * em que participam). Decisão V do idealizador: "no mapa conceitual um esteio bom é fonte de
 * inúmeras relações com outros conceitos". Ver docs/valor-conhecimento.md §5.
 */
function esteios_listar(): void
{
    $pdo    = kdd_db();
    $uid    = kdd_universo_req($pdo);
    $idioma = kdd_idioma_req();
    $pais   = kdd_pais_req();
    $limite = isset($_GET['limite']) ? max(1, min(200, (int) $_GET['limite'])) : 20;

    // Calculado ANTES da query: embutir `$x = ... ? ... : ''` dentro da concatenação cai na
    // precedência do ternário em PHP e a variável sai indefinida.
    $filtroPais = kdd_sql_filtro_pais('c.pais', $pais);
    $andPais    = $filtroPais !== '' ? " AND $filtroPais" : '';

    $s = $pdo->prepare(
        "SELECT c.id, c.sentido, c.desabilitado, c.pais,
                " . kdd_sql_rotulo('c.id', $idioma) . " AS rotulo,
                (SELECT GROUP_CONCAT(DISTINCT a.nome ORDER BY a.nome SEPARATOR ', ')
                   FROM conceito_area ca JOIN area a ON a.id = ca.area_id
                  WHERE ca.conceito_id = c.id) AS areas
           FROM conceito c
           JOIN vw_grau_conceito g ON g.conceito_id = c.id
          WHERE c.desabilitado = 0 AND c.universo_id = ?" . $andPais . "
          ORDER BY (g.grau_saida + g.grau_entrada) DESC, c.id
          LIMIT $limite"
    );
    $s->execute([$uid]);
    $conceitos = kdd_enriquecer_conceitos($pdo, array_map(static function (array $r): array {
        return ['id' => (int) $r['id'], 'rotulo' => $r['rotulo'], 'sentido' => $r['sentido'],
                'areas' => $r['areas'], 'pais' => $r['pais'],
                'desabilitado' => (int) $r['desabilitado']];
    }, $s->fetchAll()));

    json_out(['universo' => kdd_universo_resumo($pdo, $uid),
              'idioma' => $idioma ?: null, 'pais' => $pais ?: null,
              'esteios' => $conceitos]);
}

/* ───────────────────────── Catálogo de trilhas ───────────────────────── */

/**
 * GET /catalogo — o catálogo de termos/paths conhecidos por trilha
 * (api/data/catalogo_trilhas.json, versionado no repo e curável em PR).
 * O bot consome por aqui ao processar fontes (Passo 1 — docs/catalogo-trilhas.md);
 * o arquivo NÃO é empacotado no deploy do bot.
 */
function catalogo_obter(): void
{
    $arquivo = APP_ROOT . '/data/catalogo_trilhas.json';
    if (!is_file($arquivo)) {
        json_error('Catálogo não disponível neste deploy', 404);
    }
    $dados = json_decode((string) file_get_contents($arquivo), true);
    if (!is_array($dados) || !isset($dados['trilhas'])) {
        json_error('Catálogo malformado', 500);
    }
    json_out($dados);
}
