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
    $pdo  = kdd_db();
    $rows = $pdo->query("SELECT id, nome, parent_id FROM area ORDER BY nome")->fetchAll();

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

    json_out(['areas' => $raiz]);
}

/* ─────────────────────── Conceitos ──────────────────────── */

/**
 * GET /conceitos — lista conceitos com rótulos e áreas.
 * Filtros opcionais: ?q=<texto> (busca por rótulo), ?area=<id>.
 */
function conceitos_listar(): void
{
    $pdo    = kdd_db();
    $q      = trim((string) ($_GET['q']    ?? ''));
    $areaId = isset($_GET['area']) && $_GET['area'] !== '' ? (int) $_GET['area'] : null;

    $where  = [];
    $params = [];

    if ($q !== '') {
        $where[]  = "EXISTS (SELECT 1 FROM rotulo rq WHERE rq.conceito_id = c.id AND rq.texto LIKE ?)";
        $params[] = '%' . $q . '%';
    }
    if ($areaId !== null) {
        $where[]  = "EXISTS (SELECT 1 FROM conceito_area cq WHERE cq.conceito_id = c.id AND cq.area_id = ?)";
        $params[] = $areaId;
    }

    $sql = "SELECT c.id, c.sentido,
                   GROUP_CONCAT(DISTINCT r.texto ORDER BY r.principal DESC, r.texto SEPARATOR ', ') AS rotulos,
                   GROUP_CONCAT(DISTINCT a.nome  ORDER BY a.nome SEPARATOR ', ')                    AS areas
              FROM conceito c
              LEFT JOIN rotulo r        ON r.conceito_id = c.id
              LEFT JOIN conceito_area ca ON ca.conceito_id = c.id
              LEFT JOIN area a          ON a.id = ca.area_id";
    if ($where) {
        $sql .= " WHERE " . implode(' AND ', $where);
    }
    $sql .= " GROUP BY c.id, c.sentido ORDER BY c.id";

    $stmt = $pdo->prepare($sql);
    $stmt->execute($params);

    $conceitos = array_map(static function (array $row): array {
        $row['id'] = (int) $row['id'];
        return $row;
    }, $stmt->fetchAll());

    json_out(['conceitos' => $conceitos]);
}

/**
 * GET /conceitos/{id} — detalhe: rótulos, áreas, fontes que o introduziram,
 * e proposições onde participa (como origem e como destino) com a certeza.
 */
function conceitos_obter(int $id): void
{
    $pdo  = kdd_db();
    $stmt = $pdo->prepare("SELECT id, sentido, criado_em FROM conceito WHERE id = ?");
    $stmt->execute([$id]);
    $conceito = $stmt->fetch();
    if (!$conceito) {
        json_error('Conceito não encontrado', 404);
    }
    $conceito['id'] = (int) $conceito['id'];

    // Rótulos
    $s = $pdo->prepare("SELECT id, texto, principal FROM rotulo WHERE conceito_id = ? ORDER BY principal DESC, texto");
    $s->execute([$id]);
    $conceito['rotulos'] = array_map(static function (array $r): array {
        return ['id' => (int) $r['id'], 'texto' => $r['texto'], 'principal' => (bool) $r['principal']];
    }, $s->fetchAll());

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
    $conceito['proposicoes_origem'] = kdd_proposicoes_do_conceito($pdo, $id, 'origem');
    // Proposições onde é DESTINO
    $conceito['proposicoes_destino'] = kdd_proposicoes_do_conceito($pdo, $id, 'destino');

    json_out(['conceito' => $conceito]);
}

/**
 * Proposições em que o conceito participa, com o rótulo da "outra ponta" e a certeza.
 * $lado = 'origem' → lista as que saem do conceito; 'destino' → as que chegam nele.
 */
function kdd_proposicoes_do_conceito(PDO $pdo, int $conceitoId, string $lado): array
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

    $sql = "SELECT p.id, p.relacao, p.$col_outro AS outro_id,
                   (SELECT texto FROM rotulo WHERE conceito_id = p.$col_outro
                     ORDER BY principal DESC, id LIMIT 1) AS outro_rotulo,
                   v.fontes_aprovadas
              FROM proposicao p
              JOIN vw_certeza_proposicao v ON v.proposicao_id = p.id
             WHERE p.$col_self = ?
             ORDER BY v.fontes_aprovadas DESC, p.id";
    $s = $pdo->prepare($sql);
    $s->execute([$conceitoId]);

    return array_map(static function (array $r) use ($chave): array {
        return [
            'proposicao_id'    => (int) $r['id'],
            'relacao'          => $r['relacao'],
            $chave             => ['id' => (int) $r['outro_id'], 'rotulo' => $r['outro_rotulo']],
            'fontes_aprovadas' => (int) $r['fontes_aprovadas'],
        ];
    }, $s->fetchAll());
}

/* ────────────────────── Proposições ─────────────────────── */

/**
 * GET /proposicoes — lista proposições com certeza (da view).
 * Filtro opcional ?conceito=<id> (origem OU destino).
 */
function proposicoes_listar(): void
{
    $pdo       = kdd_db();
    $conceito  = isset($_GET['conceito']) && $_GET['conceito'] !== '' ? (int) $_GET['conceito'] : null;

    $sql = "SELECT p.id, p.relacao,
                   p.conceito_origem,
                   (SELECT texto FROM rotulo WHERE conceito_id = p.conceito_origem
                     ORDER BY principal DESC, id LIMIT 1) AS origem_rotulo,
                   p.conceito_destino,
                   (SELECT texto FROM rotulo WHERE conceito_id = p.conceito_destino
                     ORDER BY principal DESC, id LIMIT 1) AS destino_rotulo,
                   v.fontes_aprovadas
              FROM proposicao p
              JOIN vw_certeza_proposicao v ON v.proposicao_id = p.id";
    $params = [];
    if ($conceito !== null) {
        $sql      .= " WHERE p.conceito_origem = ? OR p.conceito_destino = ?";
        $params    = [$conceito, $conceito];
    }
    $sql .= " ORDER BY v.fontes_aprovadas DESC, p.id";

    $stmt = $pdo->prepare($sql);
    $stmt->execute($params);

    $proposicoes = array_map(static function (array $r): array {
        return [
            'id'               => (int) $r['id'],
            'relacao'          => $r['relacao'],
            'origem'           => ['id' => (int) $r['conceito_origem'],  'rotulo' => $r['origem_rotulo']],
            'destino'          => ['id' => (int) $r['conceito_destino'], 'rotulo' => $r['destino_rotulo']],
            'fontes_aprovadas' => (int) $r['fontes_aprovadas'],
        ];
    }, $stmt->fetchAll());

    json_out(['proposicoes' => $proposicoes]);
}

/**
 * GET /fontes/{id}/mapa — conceitos e proposições de uma fonte (documento),
 * para desenhar o mapa conceitual inteiro daquele PDF. Os conceitos saem de
 * conceito_fonte; as proposições, das referências da própria fonte (com certeza).
 */
function fonte_mapa(int $id): void
{
    $pdo = kdd_db();
    $s = $pdo->prepare("SELECT id, titulo FROM fonte WHERE id = ?");
    $s->execute([$id]);
    $fonte = $s->fetch();
    if (!$fonte) {
        json_error('Fonte não encontrada', 404);
    }

    $s = $pdo->prepare(
        "SELECT c.id, c.sentido,
                (SELECT texto FROM rotulo WHERE conceito_id = c.id ORDER BY principal DESC, id LIMIT 1) AS rotulo,
                GROUP_CONCAT(DISTINCT a.nome ORDER BY a.nome SEPARATOR ', ') AS areas
           FROM conceito_fonte cf
           JOIN conceito c          ON c.id = cf.conceito_id
           LEFT JOIN conceito_area ca ON ca.conceito_id = c.id
           LEFT JOIN area a         ON a.id = ca.area_id
          WHERE cf.fonte_id = ?
          GROUP BY c.id, c.sentido ORDER BY c.id"
    );
    $s->execute([$id]);
    $conceitos = array_map(static function (array $r): array {
        return ['id' => (int) $r['id'], 'rotulo' => $r['rotulo'], 'sentido' => $r['sentido'], 'areas' => $r['areas']];
    }, $s->fetchAll());

    $s = $pdo->prepare(
        "SELECT p.id, p.relacao,
                p.conceito_origem  AS origem_id,
                (SELECT texto FROM rotulo WHERE conceito_id = p.conceito_origem  ORDER BY principal DESC, id LIMIT 1) AS origem_rotulo,
                p.conceito_destino AS destino_id,
                (SELECT texto FROM rotulo WHERE conceito_id = p.conceito_destino ORDER BY principal DESC, id LIMIT 1) AS destino_rotulo,
                v.fontes_aprovadas
           FROM referencia rf
           JOIN proposicao p ON p.id = rf.proposicao_id
           JOIN vw_certeza_proposicao v ON v.proposicao_id = p.id
          WHERE rf.fonte_id = ?
          ORDER BY p.id"
    );
    $s->execute([$id]);
    $proposicoes = array_map(static function (array $r): array {
        return [
            'id'               => (int) $r['id'],
            'relacao'          => $r['relacao'],
            'origem'           => ['id' => (int) $r['origem_id'],  'rotulo' => $r['origem_rotulo']],
            'destino'          => ['id' => (int) $r['destino_id'], 'rotulo' => $r['destino_rotulo']],
            'fontes_aprovadas' => (int) $r['fontes_aprovadas'],
        ];
    }, $s->fetchAll());

    json_out(['fonte' => ['id' => (int) $fonte['id'], 'titulo' => $fonte['titulo']],
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
    $pdo = kdd_db();

    // Áreas com contagem de conceitos
    $areas = $pdo->query(
        "SELECT a.id, a.nome, COUNT(DISTINCT ca.conceito_id) AS conceitos
           FROM area a
           LEFT JOIN conceito_area ca ON ca.area_id = a.id
          GROUP BY a.id, a.nome ORDER BY a.nome"
    )->fetchAll();
    $areas = array_map(static function (array $a): array {
        return ['id' => (int) $a['id'], 'nome' => $a['nome'], 'conceitos' => (int) $a['conceitos']];
    }, $areas);

    // Pontes interdisciplinares: proposições cuja origem e destino não compartilham área.
    $pontes = $pdo->query(
        "SELECT p.id, p.relacao,
                p.conceito_origem  AS origem_id,
                (SELECT texto FROM rotulo WHERE conceito_id = p.conceito_origem  ORDER BY principal DESC, id LIMIT 1) AS origem_rotulo,
                p.conceito_destino AS destino_id,
                (SELECT texto FROM rotulo WHERE conceito_id = p.conceito_destino ORDER BY principal DESC, id LIMIT 1) AS destino_rotulo
           FROM proposicao p
          WHERE NOT EXISTS (
                  SELECT 1 FROM conceito_area cao
                    JOIN conceito_area cad ON cad.area_id = cao.area_id
                   WHERE cao.conceito_id = p.conceito_origem
                     AND cad.conceito_id = p.conceito_destino)
          ORDER BY p.id"
    )->fetchAll();
    $pontes = array_map(static function (array $r): array {
        return [
            'proposicao_id' => (int) $r['id'],
            'relacao'       => $r['relacao'],
            'origem'        => ['id' => (int) $r['origem_id'],  'rotulo' => $r['origem_rotulo']],
            'destino'       => ['id' => (int) $r['destino_id'], 'rotulo' => $r['destino_rotulo']],
        ];
    }, $pontes);

    // Homônimos: mesmo texto de rótulo apontando para conceitos (sentidos) diferentes.
    $homonimos = $pdo->query(
        "SELECT r.texto, COUNT(DISTINCT r.conceito_id) AS sentidos,
                GROUP_CONCAT(DISTINCT r.conceito_id ORDER BY r.conceito_id SEPARATOR ',') AS conceito_ids
           FROM rotulo r
          GROUP BY r.texto
         HAVING COUNT(DISTINCT r.conceito_id) > 1
          ORDER BY sentidos DESC, r.texto"
    )->fetchAll();
    $homonimos = array_map(static function (array $h): array {
        return [
            'rotulo'       => $h['texto'],
            'sentidos'     => (int) $h['sentidos'],
            'conceito_ids' => array_map('intval', explode(',', $h['conceito_ids'])),
        ];
    }, $homonimos);

    json_out([
        'areas'     => $areas,
        'pontes'    => $pontes,
        'homonimos' => $homonimos,
    ]);
}
