<?php
declare(strict_types=1);

/**
 * Camada VETORIAL (docs/valor-conhecimento.md §6): embeddings de conceitos e pares de
 * conceitos semelhantes. A API só GUARDA e SERVE; quem embute e calcula o cosseno é o bot
 * (kdd_bot/vetor.py, `main.py --vetorizar`), porque a Hostinger não tem tipo VECTOR nem Ollama.
 */

/**
 * GET /embeddings?modelo=M[&faltando=1]
 *  - sem faltando: todos os vetores de conceitos para o modelo → {modelo, embeddings:[{conceito_id, vetor}]}
 *  - faltando=1:   conceitos SEM vetor nesse modelo (habilitados) → {modelo, conceitos:[{id, rotulo, sentido}]}
 */
function embeddings_listar(): void
{
    $pdo    = kdd_db();
    $idioma = kdd_idioma_req();
    $modelo = trim((string) ($_GET['modelo'] ?? ''));
    if ($modelo === '') {
        json_error('Informe ?modelo=', 400);
    }
    if (!empty($_GET['faltando'])) {
        // Sem ?idioma=, o rótulo sai no idioma-BASE do universo do conceito: o espaço
        // vetorial fica coerente. O modelo padrão não é multilíngue (spec §8), então
        // misturar idiomas aqui enfraqueceria a similaridade.
        $s = $pdo->prepare(
            "SELECT c.id, c.sentido, c.pais,
                    " . kdd_sql_rotulo('c.id', $idioma) . " AS rotulo
               FROM conceito c
              WHERE c.desabilitado = 0
                AND NOT EXISTS (SELECT 1 FROM embedding e
                                 WHERE e.alvo_tipo = 'conceito' AND e.alvo_id = c.id AND e.modelo = ?)
              ORDER BY c.id"
        );
        $s->execute([$modelo]);
        $rows = array_map(static fn(array $r): array => [
            'id' => (int) $r['id'], 'rotulo' => $r['rotulo'], 'sentido' => $r['sentido'],
            'pais' => $r['pais'],
        ], $s->fetchAll());
        json_out(['modelo' => $modelo, 'conceitos' => $rows]);
    }

    $s = $pdo->prepare(
        "SELECT e.alvo_id, e.dim, e.vetor FROM embedding e
           JOIN conceito c ON c.id = e.alvo_id
          WHERE e.alvo_tipo = 'conceito' AND e.modelo = ? AND c.desabilitado = 0
          ORDER BY e.alvo_id"
    );
    $s->execute([$modelo]);
    $rows = [];
    foreach ($s->fetchAll() as $r) {
        $rows[] = ['conceito_id' => (int) $r['alvo_id'], 'dim' => (int) $r['dim'],
                   'vetor' => json_decode((string) $r['vetor'], true)];
    }
    json_out(['modelo' => $modelo, 'embeddings' => $rows]);
}

/** PUT /conceitos/{id}/embedding  { modelo, vetor: [float, ...] } — upsert. */
function embedding_gravar(int $id): void
{
    $pdo  = kdd_db();
    $body = json_body();
    $modelo = trim((string) ($body['modelo'] ?? ''));
    $vetor  = $body['vetor'] ?? null;
    if ($modelo === '' || !is_array($vetor) || !$vetor) {
        json_error('Informe modelo e vetor (array numérico não vazio)', 400);
    }
    foreach ($vetor as $v) {
        if (!is_int($v) && !is_float($v)) {
            json_error('vetor deve conter apenas números', 400);
        }
    }
    $s = $pdo->prepare("SELECT id FROM conceito WHERE id = ?");
    $s->execute([$id]);
    if (!$s->fetch()) {
        json_error('Conceito não encontrado', 404);
    }
    $pdo->prepare(
        "INSERT INTO embedding (alvo_tipo, alvo_id, modelo, dim, vetor)
         VALUES ('conceito', ?, ?, ?, ?)
         ON DUPLICATE KEY UPDATE dim = VALUES(dim), vetor = VALUES(vetor)"
    )->execute([$id, $modelo, count($vetor), json_encode(array_values($vetor))]);
    json_out(['ok' => true, 'conceito_id' => $id, 'modelo' => $modelo, 'dim' => count($vetor)]);
}

/**
 * PUT /similares  { modelo, pares: [{a, b, similaridade}] } — SUBSTITUI todos os pares do
 * modelo (o bot recalcula tudo a cada passada; N é pequeno). a<b é normalizado aqui.
 */
function similares_gravar(): void
{
    $pdo  = kdd_db();
    $body = json_body();
    $modelo = trim((string) ($body['modelo'] ?? ''));
    $pares  = $body['pares'] ?? null;
    if ($modelo === '' || !is_array($pares)) {
        json_error('Informe modelo e pares (array)', 400);
    }
    $pdo->beginTransaction();
    try {
        $pdo->prepare("DELETE FROM conceito_similar WHERE modelo = ?")->execute([$modelo]);
        $ins = $pdo->prepare(
            "INSERT INTO conceito_similar (conceito_a, conceito_b, modelo, similaridade) VALUES (?, ?, ?, ?)
             ON DUPLICATE KEY UPDATE similaridade = VALUES(similaridade), calculado_em = CURRENT_TIMESTAMP"
        );
        $n = 0;
        foreach ($pares as $p) {
            $a = (int) ($p['a'] ?? 0);
            $b = (int) ($p['b'] ?? 0);
            $sim = (float) ($p['similaridade'] ?? 0);
            if ($a <= 0 || $b <= 0 || $a === $b) {
                continue;
            }
            if ($a > $b) {
                [$a, $b] = [$b, $a];
            }
            $ins->execute([$a, $b, $modelo, max(0.0, min(1.0, $sim))]);
            $n++;
        }
        $pdo->commit();
    } catch (Throwable $e) {
        $pdo->rollBack();
        json_erro_interno($e, 'gravar similares');
    }
    json_out(['ok' => true, 'modelo' => $modelo, 'pares' => $n]);
}

/** GET /similares?min=0.85&limite=50[&modelo=M] — fila global de quase-duplicatas (sugestão de merge). */
function similares_listar(): void
{
    $pdo    = kdd_db();
    $idioma = kdd_idioma_req();
    $min    = isset($_GET['min']) ? (float) $_GET['min'] : 0.85;
    $limite = isset($_GET['limite']) ? max(1, min(500, (int) $_GET['limite'])) : 50;
    $modelo = trim((string) ($_GET['modelo'] ?? ''));

    // escopo: interno (mesmo universo = candidato a MERGE) | externo (universos diferentes
    // = CONTRAPARTE, docs/universos.md §5) | todos. O cálculo é um só; muda a leitura.
    $escopo = trim((string) ($_GET['escopo'] ?? 'interno'));
    if (!in_array($escopo, ['interno', 'externo', 'todos'], true)) {
        json_error("escopo inválido: use interno | externo | todos", 400);
    }

    $sql = "SELECT s.conceito_a, s.conceito_b, s.modelo, s.similaridade,
                   ca.universo_id AS universo_a, cb.universo_id AS universo_b,
                   ca.pais AS pais_a, cb.pais AS pais_b,
                   " . kdd_sql_rotulo('s.conceito_a', $idioma) . " AS rotulo_a,
                   ca.sentido AS sentido_a,
                   " . kdd_sql_rotulo('s.conceito_b', $idioma) . " AS rotulo_b,
                   cb.sentido AS sentido_b
              FROM conceito_similar s
              JOIN conceito ca ON ca.id = s.conceito_a
              JOIN conceito cb ON cb.id = s.conceito_b
             WHERE s.similaridade >= ?";
    $params = [$min];
    if ($modelo !== '') {
        $sql .= " AND s.modelo = ?";
        $params[] = $modelo;
    }
    if ($escopo === 'interno') {
        $sql .= " AND ca.universo_id = cb.universo_id";
    } elseif ($escopo === 'externo') {
        $sql .= " AND ca.universo_id <> cb.universo_id";
    }
    $sql .= " ORDER BY s.similaridade DESC LIMIT $limite";
    $st = $pdo->prepare($sql);
    $st->execute($params);
    $rows = array_map(static function (array $r) use ($pdo): array {
        return [
            'a' => ['id' => (int) $r['conceito_a'], 'rotulo' => $r['rotulo_a'],
                    'sentido' => $r['sentido_a'], 'pais' => $r['pais_a'],
                    'universo' => kdd_universo_resumo($pdo, (int) $r['universo_a'])],
            'b' => ['id' => (int) $r['conceito_b'], 'rotulo' => $r['rotulo_b'],
                    'sentido' => $r['sentido_b'], 'pais' => $r['pais_b'],
                    'universo' => kdd_universo_resumo($pdo, (int) $r['universo_b'])],
            'similaridade'   => (float) $r['similaridade'],
            'modelo'         => $r['modelo'],
            // true = duplicata a fundir; false = contraparte em universo paralelo
            'mesmo_universo' => (int) $r['universo_a'] === (int) $r['universo_b'],
        ];
    }, $st->fetchAll());
    json_out(['min' => $min, 'escopo' => $escopo, 'similares' => $rows]);
}

/** Semelhantes de UM conceito (usado por GET /conceitos/{id}). */
function kdd_similares_do_conceito(PDO $pdo, int $id, int $limite = 10,
                                   string $idioma = ''): array
{
    // Só do MESMO universo: aqui é a fila de fusão. O gêmeo em universo paralelo sai em
    // GET /conceitos/{id}/contrapartes (docs/universos.md §5).
    $s = $pdo->prepare(
        "SELECT IF(s.conceito_a = ?, s.conceito_b, s.conceito_a) AS outro_id, s.similaridade, s.modelo
           FROM conceito_similar s
           JOIN conceito ca ON ca.id = s.conceito_a
           JOIN conceito cb ON cb.id = s.conceito_b
          WHERE (s.conceito_a = ? OR s.conceito_b = ?)
            AND ca.universo_id = cb.universo_id
          ORDER BY s.similaridade DESC LIMIT $limite"
    );
    $s->execute([$id, $id, $id]);
    $out = [];
    foreach ($s->fetchAll() as $r) {
        $o = (int) $r['outro_id'];
        $q = $pdo->prepare(
            "SELECT c.sentido, " . kdd_sql_rotulo('c.id', $idioma) . " AS rotulo
               FROM conceito c WHERE c.id = ?"
        );
        $q->execute([$o]);
        $c = $q->fetch() ?: ['sentido' => null, 'rotulo' => null];
        $out[] = ['id' => $o, 'rotulo' => $c['rotulo'], 'sentido' => $c['sentido'],
                  'similaridade' => (float) $r['similaridade'], 'modelo' => $r['modelo']];
    }
    return $out;
}
