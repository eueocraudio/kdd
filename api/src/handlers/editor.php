<?php
declare(strict_types=1);

/**
 * Editor Manual de Mapas (ver docs/editor-mapas.md).
 *
 * Princípio (decisão A): toda edição humana é atribuída a uma FONTE de origem
 * 'curadoria' — sem PDF, já aprovada. A proposição editada ganha uma referência
 * a essa fonte e entra na certeza pelo MESMO JOIN da ingestão (vw_certeza_proposicao),
 * sem caso especial. Proveniência preservada (curado por humano × afirmado por PDF).
 *
 * Escrita é ação de VALIDADOR (curador): todas as rotas exigem perfil 'validador'
 * — primeira vez que o perfil vira controle técnico (spec §6, decisão recomendada).
 *
 * Reusa de fontes.php: kdd_resolver_conceito, kdd_garantir_rotulo, kdd_upsert_area.
 */

/** Exige perfil 'validador'; encerra 403 caso contrário. */
function kdd_exigir_validador(array $auth): void
{
    if (($auth['perfil'] ?? '') !== 'validador') {
        json_error('Edição exige perfil validador', 403);
    }
}

/** Get-or-create da fonte de curadoria do autor (origem=curadoria, já aprovada). */
function kdd_fonte_curadoria(PDO $pdo, string $autor): int
{
    $autor  = trim($autor) !== '' ? trim($autor) : 'curador';
    $titulo = 'Curadoria — ' . $autor;

    $s = $pdo->prepare("SELECT id FROM fonte WHERE origem = 'curadoria' AND titulo = ? LIMIT 1");
    $s->execute([$titulo]);
    $row = $s->fetch();
    if ($row) {
        return (int) $row['id'];
    }
    $pdo->prepare(
        "INSERT INTO fonte (titulo, arquivo_caminho, origem, status_proc, status_aprovacao)
         VALUES (?, NULL, 'curadoria', 'processado', 'aprovada')"
    )->execute([$titulo]);
    return (int) $pdo->lastInsertId();
}

/** Registra um changeset (auditoria append-only). */
function kdd_log_changeset(
    PDO $pdo, array $auth, string $acao, string $alvoTipo, ?int $alvoId, $antes, $depois
): void {
    $pdo->prepare(
        "INSERT INTO changeset (autor, perfil, acao, alvo_tipo, alvo_id, antes, depois)
         VALUES (?, ?, ?, ?, ?, ?, ?)"
    )->execute([
        (string) ($auth['descricao'] ?? $auth['perfil'] ?? 'curador'),
        $auth['perfil'] ?? null,
        $acao, $alvoTipo, $alvoId,
        $antes  === null ? null : json_encode($antes,  JSON_UNESCAPED_UNICODE),
        $depois === null ? null : json_encode($depois, JSON_UNESCAPED_UNICODE),
    ]);
}

/** Certeza (nº de fontes aprovadas) de uma proposição, via a view. */
function kdd_certeza(PDO $pdo, int $propId): int
{
    $s = $pdo->prepare("SELECT fontes_aprovadas FROM vw_certeza_proposicao WHERE proposicao_id = ?");
    $s->execute([$propId]);
    return (int) ($s->fetchColumn() ?: 0);
}

/** Snapshot leve de um conceito (p/ changeset/resposta). */
function kdd_conceito_resumo(PDO $pdo, int $id): ?array
{
    $s = $pdo->prepare("SELECT id, sentido FROM conceito WHERE id = ?");
    $s->execute([$id]);
    $c = $s->fetch();
    if (!$c) {
        return null;
    }
    $r = $pdo->prepare("SELECT id, texto, principal FROM rotulo WHERE conceito_id = ? ORDER BY principal DESC, id");
    $r->execute([$id]);
    $a = $pdo->prepare(
        "SELECT a.id, a.nome FROM conceito_area ca JOIN area a ON a.id = ca.area_id WHERE ca.conceito_id = ? ORDER BY a.nome"
    );
    $a->execute([$id]);
    return ['id' => (int) $c['id'], 'sentido' => $c['sentido'],
            'rotulos' => $r->fetchAll(), 'areas' => $a->fetchAll()];
}

/** Garante que o conceito existe; senão 404. */
function kdd_assert_conceito(PDO $pdo, int $id): void
{
    $s = $pdo->prepare("SELECT id FROM conceito WHERE id = ?");
    $s->execute([$id]);
    if (!$s->fetch()) {
        json_error('Conceito não encontrado', 404);
    }
}

/* ───────────────────────── Proposições ───────────────────────── */

/** POST /proposicoes  { origem_id, relacao, destino_id } */
function proposicao_criar(array $auth): void
{
    kdd_exigir_validador($auth);
    $pdo  = kdd_db();
    $body = json_body();

    $origem  = (int) ($body['origem_id']  ?? 0);
    $destino = (int) ($body['destino_id'] ?? 0);
    $relacao = trim((string) ($body['relacao'] ?? ''));

    if ($origem <= 0 || $destino <= 0 || $relacao === '') {
        json_error('Informe origem_id, relacao e destino_id', 400);
    }
    kdd_assert_conceito($pdo, $origem);
    kdd_assert_conceito($pdo, $destino);

    $pdo->beginTransaction();
    try {
        $prop_id  = kdd_upsert_proposicao($pdo, $origem, $relacao, $destino);
        $fonte_id = kdd_fonte_curadoria($pdo, (string) ($auth['descricao'] ?? ''));

        $pdo->prepare("INSERT IGNORE INTO referencia (proposicao_id, fonte_id) VALUES (?, ?)")
            ->execute([$prop_id, $fonte_id]);
        foreach ([$origem, $destino] as $cid) {
            $pdo->prepare("INSERT IGNORE INTO conceito_fonte (conceito_id, fonte_id) VALUES (?, ?)")
                ->execute([$cid, $fonte_id]);
        }
        kdd_log_changeset($pdo, $auth, 'criar_proposicao', 'proposicao', $prop_id, null,
            ['origem_id' => $origem, 'relacao' => $relacao, 'destino_id' => $destino]);
        $pdo->commit();
    } catch (Throwable $e) {
        $pdo->rollBack();
        json_erro_interno($e, 'criar proposição');
    }

    json_out(['ok' => true, 'proposicao' => kdd_proposicao_view($pdo, $prop_id)], 201);
}

/** PATCH /proposicoes/{id}  { origem_id?, relacao?, destino_id? } */
function proposicao_editar(array $auth, int $id): void
{
    kdd_exigir_validador($auth);
    $pdo  = kdd_db();
    $body = json_body();

    $s = $pdo->prepare("SELECT id, conceito_origem, relacao, conceito_destino FROM proposicao WHERE id = ?");
    $s->execute([$id]);
    $old = $s->fetch();
    if (!$old) {
        json_error('Proposição não encontrada', 404);
    }

    $origem  = (int) ($body['origem_id']  ?? $old['conceito_origem']);
    $destino = (int) ($body['destino_id'] ?? $old['conceito_destino']);
    $relacao = trim((string) ($body['relacao'] ?? $old['relacao']));
    if ($origem <= 0 || $destino <= 0 || $relacao === '') {
        json_error('origem_id, relacao e destino_id não podem ficar vazios', 400);
    }
    kdd_assert_conceito($pdo, $origem);
    kdd_assert_conceito($pdo, $destino);

    $pdo->beginTransaction();
    try {
        $novo_id  = kdd_upsert_proposicao($pdo, $origem, $relacao, $destino);
        $fonte_id = kdd_fonte_curadoria($pdo, (string) ($auth['descricao'] ?? ''));

        if ($novo_id !== (int) $old['id']) {
            // move a referência de curadoria da antiga para a nova
            $pdo->prepare("DELETE FROM referencia WHERE proposicao_id = ? AND fonte_id = ?")
                ->execute([(int) $old['id'], $fonte_id]);
            $pdo->prepare("INSERT IGNORE INTO referencia (proposicao_id, fonte_id) VALUES (?, ?)")
                ->execute([$novo_id, $fonte_id]);
            kdd_remover_proposicao_se_orfa($pdo, (int) $old['id']);
        } else {
            // mesma tripla: só garante a referência de curadoria
            $pdo->prepare("INSERT IGNORE INTO referencia (proposicao_id, fonte_id) VALUES (?, ?)")
                ->execute([$novo_id, $fonte_id]);
        }
        kdd_log_changeset($pdo, $auth, 'editar_proposicao', 'proposicao', $novo_id,
            ['origem_id' => (int) $old['conceito_origem'], 'relacao' => $old['relacao'],
             'destino_id' => (int) $old['conceito_destino']],
            ['origem_id' => $origem, 'relacao' => $relacao, 'destino_id' => $destino]);
        $pdo->commit();
    } catch (Throwable $e) {
        $pdo->rollBack();
        json_erro_interno($e, 'editar proposição');
    }

    json_out(['ok' => true, 'proposicao' => kdd_proposicao_view($pdo, $novo_id)]);
}

/** DELETE /proposicoes/{id}  (remove o apoio da curadoria; some se ficar órfã) */
function proposicao_remover(array $auth, int $id): void
{
    kdd_exigir_validador($auth);
    $pdo = kdd_db();

    $s = $pdo->prepare("SELECT id, conceito_origem, relacao, conceito_destino FROM proposicao WHERE id = ?");
    $s->execute([$id]);
    $old = $s->fetch();
    if (!$old) {
        json_error('Proposição não encontrada', 404);
    }

    $pdo->beginTransaction();
    try {
        $fonte_id = kdd_fonte_curadoria($pdo, (string) ($auth['descricao'] ?? ''));
        $pdo->prepare("DELETE FROM referencia WHERE proposicao_id = ? AND fonte_id = ?")
            ->execute([$id, $fonte_id]);
        $removida = kdd_remover_proposicao_se_orfa($pdo, $id);
        kdd_log_changeset($pdo, $auth, 'remover_proposicao', 'proposicao', $id,
            ['origem_id' => (int) $old['conceito_origem'], 'relacao' => $old['relacao'],
             'destino_id' => (int) $old['conceito_destino']], null);
        $pdo->commit();
    } catch (Throwable $e) {
        $pdo->rollBack();
        json_erro_interno($e, 'remover proposição');
    }

    json_out(['ok' => true, 'proposicao_removida' => $removida,
              'certeza' => $removida ? 0 : kdd_certeza($pdo, $id)]);
}

/** Upsert idempotente de uma proposição (origem+relacao+destino). Retorna o id. */
function kdd_upsert_proposicao(PDO $pdo, int $origem, string $relacao, int $destino): int
{
    $s = $pdo->prepare(
        "SELECT id FROM proposicao WHERE conceito_origem = ? AND relacao = ? AND conceito_destino = ? LIMIT 1"
    );
    $s->execute([$origem, $relacao, $destino]);
    $row = $s->fetch();
    if ($row) {
        return (int) $row['id'];
    }
    $pdo->prepare(
        "INSERT INTO proposicao (conceito_origem, relacao, conceito_destino) VALUES (?, ?, ?)"
    )->execute([$origem, $relacao, $destino]);
    return (int) $pdo->lastInsertId();
}

/** Apaga a proposição se nenhuma referência a sustenta. Retorna true se apagou. */
function kdd_remover_proposicao_se_orfa(PDO $pdo, int $propId): bool
{
    $s = $pdo->prepare("SELECT COUNT(*) FROM referencia WHERE proposicao_id = ?");
    $s->execute([$propId]);
    if ((int) $s->fetchColumn() > 0) {
        return false;
    }
    $pdo->prepare("DELETE FROM proposicao WHERE id = ?")->execute([$propId]);
    return true;
}

/** View de uma proposição com rótulos das pontas e certeza. */
function kdd_proposicao_view(PDO $pdo, int $id): ?array
{
    $s = $pdo->prepare(
        "SELECT p.id, p.relacao,
                p.conceito_origem  AS origem_id,
                p.conceito_destino AS destino_id,
                (SELECT texto FROM rotulo WHERE conceito_id = p.conceito_origem  ORDER BY principal DESC, id LIMIT 1) AS origem_rotulo,
                (SELECT texto FROM rotulo WHERE conceito_id = p.conceito_destino ORDER BY principal DESC, id LIMIT 1) AS destino_rotulo
           FROM proposicao p WHERE p.id = ?"
    );
    $s->execute([$id]);
    $p = $s->fetch();
    if (!$p) {
        return null;
    }
    $p['certeza'] = kdd_certeza($pdo, $id);
    return $p;
}

/* ───────────────────────── Conceitos ───────────────────────── */

/** POST /conceitos  { sentido, rotulo_principal, areas?: [nomes] } */
function conceito_criar(array $auth): void
{
    kdd_exigir_validador($auth);
    $pdo  = kdd_db();
    $body = json_body();

    $sentido = trim((string) ($body['sentido'] ?? ''));
    $rotulo  = trim((string) ($body['rotulo_principal'] ?? ''));
    $areas   = is_array($body['areas'] ?? null) ? $body['areas'] : [];
    if ($sentido === '' || $rotulo === '') {
        json_error('Informe sentido e rotulo_principal', 400);
    }

    $s = $pdo->prepare("SELECT id FROM conceito WHERE sentido = ? LIMIT 1");
    $s->execute([$sentido]);
    if ($s->fetch()) {
        json_error('Já existe um conceito com esse sentido', 409);
    }

    $pdo->beginTransaction();
    try {
        $pdo->prepare("INSERT INTO conceito (sentido) VALUES (?)")->execute([$sentido]);
        $cid = (int) $pdo->lastInsertId();
        kdd_garantir_rotulo($pdo, $cid, $rotulo, true);
        foreach ($areas as $nome) {
            $nome = trim((string) $nome);
            if ($nome === '') { continue; }
            $aid = kdd_upsert_area($pdo, $nome);
            $pdo->prepare("INSERT IGNORE INTO conceito_area (conceito_id, area_id) VALUES (?, ?)")
                ->execute([$cid, $aid]);
        }
        $fonte_id = kdd_fonte_curadoria($pdo, (string) ($auth['descricao'] ?? ''));
        $pdo->prepare("INSERT IGNORE INTO conceito_fonte (conceito_id, fonte_id) VALUES (?, ?)")
            ->execute([$cid, $fonte_id]);
        kdd_log_changeset($pdo, $auth, 'criar_conceito', 'conceito', $cid, null,
            ['sentido' => $sentido, 'rotulo_principal' => $rotulo, 'areas' => $areas]);
        $pdo->commit();
    } catch (Throwable $e) {
        $pdo->rollBack();
        json_erro_interno($e, 'criar conceito');
    }

    json_out(['ok' => true, 'conceito' => kdd_conceito_resumo($pdo, $cid)], 201);
}

/** PATCH /conceitos/{id}  { sentido } */
function conceito_editar(array $auth, int $id): void
{
    kdd_exigir_validador($auth);
    $pdo  = kdd_db();
    $body = json_body();
    kdd_assert_conceito($pdo, $id);

    $antes = kdd_conceito_resumo($pdo, $id);
    if (isset($body['sentido'])) {
        $sentido = trim((string) $body['sentido']);
        if ($sentido === '') {
            json_error('sentido não pode ficar vazio', 400);
        }
        $s = $pdo->prepare("SELECT id FROM conceito WHERE sentido = ? AND id <> ? LIMIT 1");
        $s->execute([$sentido, $id]);
        if ($s->fetch()) {
            json_error('Outro conceito já usa esse sentido', 409);
        }
        $pdo->prepare("UPDATE conceito SET sentido = ? WHERE id = ?")->execute([$sentido, $id]);
    }
    kdd_log_changeset($pdo, $auth, 'editar_conceito', 'conceito', $id, $antes, kdd_conceito_resumo($pdo, $id));
    json_out(['ok' => true, 'conceito' => kdd_conceito_resumo($pdo, $id)]);
}

/** POST /conceitos/{id}/rotulos  { texto, principal? } */
function conceito_add_rotulo(array $auth, int $id): void
{
    kdd_exigir_validador($auth);
    $pdo  = kdd_db();
    $body = json_body();
    kdd_assert_conceito($pdo, $id);

    $texto     = trim((string) ($body['texto'] ?? ''));
    $principal = (bool) ($body['principal'] ?? false);
    if ($texto === '') {
        json_error('Informe o texto do rótulo', 400);
    }
    if ($principal) {
        $pdo->prepare("UPDATE rotulo SET principal = 0 WHERE conceito_id = ?")->execute([$id]);
    }
    kdd_garantir_rotulo($pdo, $id, $texto, $principal);
    if ($principal) {
        // Se o rótulo JÁ existia, kdd_garantir_rotulo retorna cedo sem marcá-lo
        // principal — o UPDATE acima zerou todos e o conceito ficaria sem principal.
        // Garante explicitamente que este rótulo é o principal.
        $pdo->prepare("UPDATE rotulo SET principal = 1 WHERE conceito_id = ? AND texto = ?")
            ->execute([$id, $texto]);
    }
    kdd_log_changeset($pdo, $auth, 'add_rotulo', 'conceito', $id, null, ['texto' => $texto, 'principal' => $principal]);
    json_out(['ok' => true, 'conceito' => kdd_conceito_resumo($pdo, $id)], 201);
}

/** PATCH /rotulos/{id}  { principal: true }  (define este como principal) */
function rotulo_editar(array $auth, int $id): void
{
    kdd_exigir_validador($auth);
    $pdo  = kdd_db();
    $body = json_body();

    $s = $pdo->prepare("SELECT id, conceito_id, texto FROM rotulo WHERE id = ?");
    $s->execute([$id]);
    $r = $s->fetch();
    if (!$r) {
        json_error('Rótulo não encontrado', 404);
    }
    if (($body['principal'] ?? false)) {
        $pdo->prepare("UPDATE rotulo SET principal = 0 WHERE conceito_id = ?")->execute([(int) $r['conceito_id']]);
        $pdo->prepare("UPDATE rotulo SET principal = 1 WHERE id = ?")->execute([$id]);
    }
    kdd_log_changeset($pdo, $auth, 'rotulo_principal', 'conceito', (int) $r['conceito_id'], null, ['rotulo_id' => $id]);
    json_out(['ok' => true, 'conceito' => kdd_conceito_resumo($pdo, (int) $r['conceito_id'])]);
}

/** DELETE /rotulos/{id}  (bloqueia remover o último rótulo) */
function rotulo_remover(array $auth, int $id): void
{
    kdd_exigir_validador($auth);
    $pdo = kdd_db();

    $s = $pdo->prepare("SELECT id, conceito_id, texto FROM rotulo WHERE id = ?");
    $s->execute([$id]);
    $r = $s->fetch();
    if (!$r) {
        json_error('Rótulo não encontrado', 404);
    }
    $cid = (int) $r['conceito_id'];
    $c = $pdo->prepare("SELECT COUNT(*) FROM rotulo WHERE conceito_id = ?");
    $c->execute([$cid]);
    if ((int) $c->fetchColumn() <= 1) {
        json_error('Não é possível remover o último rótulo do conceito', 409);
    }
    $pdo->prepare("DELETE FROM rotulo WHERE id = ?")->execute([$id]);
    kdd_log_changeset($pdo, $auth, 'remover_rotulo', 'conceito', $cid, ['texto' => $r['texto']], null);
    json_out(['ok' => true, 'conceito' => kdd_conceito_resumo($pdo, $cid)]);
}

/** POST /conceitos/{id}/areas  { nome }  (ou { area_id }) */
function conceito_add_area(array $auth, int $id): void
{
    kdd_exigir_validador($auth);
    $pdo  = kdd_db();
    $body = json_body();
    kdd_assert_conceito($pdo, $id);

    if (isset($body['area_id'])) {
        $aid = (int) $body['area_id'];
        $chk = $pdo->prepare("SELECT id FROM area WHERE id = ?");
        $chk->execute([$aid]);
        if (!$chk->fetch()) {
            json_error('Área não encontrada', 404);
        }
    } else {
        $nome = trim((string) ($body['nome'] ?? ''));
        if ($nome === '') {
            json_error('Informe nome ou area_id', 400);
        }
        $aid = kdd_upsert_area($pdo, $nome);
    }
    $pdo->prepare("INSERT IGNORE INTO conceito_area (conceito_id, area_id) VALUES (?, ?)")->execute([$id, $aid]);
    kdd_log_changeset($pdo, $auth, 'add_area', 'conceito', $id, null, ['area_id' => $aid]);
    json_out(['ok' => true, 'conceito' => kdd_conceito_resumo($pdo, $id)], 201);
}

/** DELETE /conceitos/{id}/areas/{area_id} */
function conceito_rem_area(array $auth, int $id, int $areaId): void
{
    kdd_exigir_validador($auth);
    $pdo = kdd_db();
    kdd_assert_conceito($pdo, $id);
    $pdo->prepare("DELETE FROM conceito_area WHERE conceito_id = ? AND area_id = ?")->execute([$id, $areaId]);
    kdd_log_changeset($pdo, $auth, 'remover_area', 'conceito', $id, ['area_id' => $areaId], null);
    json_out(['ok' => true, 'conceito' => kdd_conceito_resumo($pdo, $id)]);
}

/**
 * POST /conceitos/{id}/merge  { outro_id }
 * Mescla 'outro' em 'id': reaponta rótulos, áreas, proposições, referências e
 * proveniência; depois remove 'outro'. Transacional e idempotente.
 */
function conceito_merge(array $auth, int $id): void
{
    kdd_exigir_validador($auth);
    $pdo  = kdd_db();
    $body = json_body();
    $outro = (int) ($body['outro_id'] ?? 0);

    if ($outro <= 0 || $outro === $id) {
        json_error('Informe outro_id diferente do conceito alvo', 400);
    }
    kdd_assert_conceito($pdo, $id);
    kdd_assert_conceito($pdo, $outro);

    $antes = ['alvo' => kdd_conceito_resumo($pdo, $id), 'outro' => kdd_conceito_resumo($pdo, $outro)];

    $pdo->beginTransaction();
    try {
        // rótulos: move os que não colidem no alvo; remove os duplicados
        $rs = $pdo->prepare("SELECT id, texto FROM rotulo WHERE conceito_id = ?");
        $rs->execute([$outro]);
        foreach ($rs->fetchAll() as $r) {
            $dup = $pdo->prepare("SELECT id FROM rotulo WHERE conceito_id = ? AND texto = ? LIMIT 1");
            $dup->execute([$id, $r['texto']]);
            if ($dup->fetch()) {
                $pdo->prepare("DELETE FROM rotulo WHERE id = ?")->execute([(int) $r['id']]);
            } else {
                $pdo->prepare("UPDATE rotulo SET conceito_id = ?, principal = 0 WHERE id = ?")
                    ->execute([$id, (int) $r['id']]);
            }
        }
        // áreas e proveniência: INSERT IGNORE no alvo, apaga do outro
        $pdo->prepare("INSERT IGNORE INTO conceito_area (conceito_id, area_id) SELECT ?, area_id FROM conceito_area WHERE conceito_id = ?")
            ->execute([$id, $outro]);
        $pdo->prepare("DELETE FROM conceito_area WHERE conceito_id = ?")->execute([$outro]);
        $pdo->prepare("INSERT IGNORE INTO conceito_fonte (conceito_id, fonte_id) SELECT ?, fonte_id FROM conceito_fonte WHERE conceito_id = ?")
            ->execute([$id, $outro]);
        $pdo->prepare("DELETE FROM conceito_fonte WHERE conceito_id = ?")->execute([$outro]);

        // proposições: reaponta as pontas de 'outro' p/ 'id', deduplicando triplas
        kdd_reaponta_proposicoes($pdo, $outro, $id);

        $pdo->prepare("DELETE FROM conceito WHERE id = ?")->execute([$outro]);
        kdd_log_changeset($pdo, $auth, 'merge_conceito', 'conceito', $id, $antes, kdd_conceito_resumo($pdo, $id));
        $pdo->commit();
    } catch (Throwable $e) {
        $pdo->rollBack();
        json_erro_interno($e, 'mesclar conceito');
    }

    json_out(['ok' => true, 'conceito' => kdd_conceito_resumo($pdo, $id)]);
}

/**
 * Reaponta toda proposição em que 'de' é origem ou destino para 'para',
 * deduplicando triplas resultantes (move referências do duplicado e o apaga).
 */
function kdd_reaponta_proposicoes(PDO $pdo, int $de, int $para): void
{
    $sel = $pdo->prepare(
        "SELECT id, conceito_origem, relacao, conceito_destino
           FROM proposicao WHERE conceito_origem = ? OR conceito_destino = ?"
    );
    $sel->execute([$de, $de]);
    foreach ($sel->fetchAll() as $p) {
        $no = (int) $p['conceito_origem']  === $de ? $para : (int) $p['conceito_origem'];
        $nd = (int) $p['conceito_destino'] === $de ? $para : (int) $p['conceito_destino'];

        // Auto-laço resultante do merge (ex.: A→B com A mesclado em B vira B→B):
        // proposição sem sentido — remove-a e às suas referências em vez de gravar.
        if ($no === $nd) {
            $pdo->prepare("DELETE FROM referencia WHERE proposicao_id = ?")->execute([(int) $p['id']]);
            $pdo->prepare("DELETE FROM proposicao WHERE id = ?")->execute([(int) $p['id']]);
            continue;
        }

        $ex = $pdo->prepare(
            "SELECT id FROM proposicao WHERE conceito_origem = ? AND relacao = ? AND conceito_destino = ? AND id <> ? LIMIT 1"
        );
        $ex->execute([$no, $p['relacao'], $nd, (int) $p['id']]);
        $dupe = $ex->fetch();

        if ($dupe) {
            // move referências do duplicado para a existente e apaga o duplicado
            $pdo->prepare("INSERT IGNORE INTO referencia (proposicao_id, fonte_id) SELECT ?, fonte_id FROM referencia WHERE proposicao_id = ?")
                ->execute([(int) $dupe['id'], (int) $p['id']]);
            $pdo->prepare("DELETE FROM referencia WHERE proposicao_id = ?")->execute([(int) $p['id']]);
            $pdo->prepare("DELETE FROM proposicao WHERE id = ?")->execute([(int) $p['id']]);
        } else {
            $pdo->prepare("UPDATE proposicao SET conceito_origem = ?, conceito_destino = ? WHERE id = ?")
                ->execute([$no, $nd, (int) $p['id']]);
        }
    }
}

/**
 * POST /conceitos/{id}/split  { sentido_novo, rotulo_principal?, rotulo_ids?: [], proposicao_ids?: [] }
 * Cria um conceito novo (homônimo desambiguado) e move para ele os rótulos e as
 * pontas de proposição selecionados que hoje pertencem a {id}.
 */
function conceito_split(array $auth, int $id): void
{
    kdd_exigir_validador($auth);
    $pdo  = kdd_db();
    $body = json_body();
    kdd_assert_conceito($pdo, $id);

    $sentido = trim((string) ($body['sentido_novo'] ?? ''));
    if ($sentido === '') {
        json_error('Informe sentido_novo', 400);
    }
    $s = $pdo->prepare("SELECT id FROM conceito WHERE sentido = ? LIMIT 1");
    $s->execute([$sentido]);
    if ($s->fetch()) {
        json_error('Já existe um conceito com esse sentido', 409);
    }
    $rotulo_ids = array_map('intval', is_array($body['rotulo_ids'] ?? null) ? $body['rotulo_ids'] : []);
    $prop_ids   = array_map('intval', is_array($body['proposicao_ids'] ?? null) ? $body['proposicao_ids'] : []);
    $rot_princ  = trim((string) ($body['rotulo_principal'] ?? ''));

    $pdo->beginTransaction();
    try {
        $pdo->prepare("INSERT INTO conceito (sentido) VALUES (?)")->execute([$sentido]);
        $novo = (int) $pdo->lastInsertId();

        foreach ($rotulo_ids as $rid) {
            $pdo->prepare("UPDATE rotulo SET conceito_id = ?, principal = 0 WHERE id = ? AND conceito_id = ?")
                ->execute([$novo, $rid, $id]);
        }
        // A origem não pode ficar sem rótulo (mesma regra do rotulo_remover).
        $rc = $pdo->prepare("SELECT COUNT(*) FROM rotulo WHERE conceito_id = ?");
        $rc->execute([$id]);
        if ((int) $rc->fetchColumn() < 1) {
            $pdo->rollBack();
            json_error('O split moveria todos os rótulos; a origem ficaria sem rótulo. Deixe ao menos um.', 409);
        }
        // Se o principal foi movido, promove um rótulo remanescente da origem.
        $pp = $pdo->prepare("SELECT COUNT(*) FROM rotulo WHERE conceito_id = ? AND principal = 1");
        $pp->execute([$id]);
        if ((int) $pp->fetchColumn() === 0) {
            $r0 = $pdo->prepare("SELECT id FROM rotulo WHERE conceito_id = ? ORDER BY id LIMIT 1");
            $r0->execute([$id]);
            if ($row0 = $r0->fetch()) {
                $pdo->prepare("UPDATE rotulo SET principal = 1 WHERE id = ?")->execute([(int) $row0['id']]);
            }
        }
        if ($rot_princ !== '') {
            kdd_garantir_rotulo($pdo, $novo, $rot_princ, true);
        } else {
            // garante ao menos um rótulo principal no conceito novo
            $r = $pdo->prepare("SELECT id FROM rotulo WHERE conceito_id = ? ORDER BY id LIMIT 1");
            $r->execute([$novo]);
            if ($row = $r->fetch()) {
                $pdo->prepare("UPDATE rotulo SET principal = 1 WHERE id = ?")->execute([(int) $row['id']]);
            } else {
                kdd_garantir_rotulo($pdo, $novo, $sentido, true);
            }
        }
        foreach ($prop_ids as $pid) {
            $pdo->prepare("UPDATE proposicao SET conceito_origem = ? WHERE id = ? AND conceito_origem = ?")
                ->execute([$novo, $pid, $id]);
            $pdo->prepare("UPDATE proposicao SET conceito_destino = ? WHERE id = ? AND conceito_destino = ?")
                ->execute([$novo, $pid, $id]);
        }
        $fonte_id = kdd_fonte_curadoria($pdo, (string) ($auth['descricao'] ?? ''));
        $pdo->prepare("INSERT IGNORE INTO conceito_fonte (conceito_id, fonte_id) VALUES (?, ?)")->execute([$novo, $fonte_id]);

        kdd_log_changeset($pdo, $auth, 'split_conceito', 'conceito', $id,
            ['origem' => $id], ['novo' => $novo, 'sentido' => $sentido,
             'rotulo_ids' => $rotulo_ids, 'proposicao_ids' => $prop_ids]);
        $pdo->commit();
    } catch (Throwable $e) {
        $pdo->rollBack();
        json_erro_interno($e, 'desambiguar (split) conceito');
    }

    json_out(['ok' => true, 'origem' => kdd_conceito_resumo($pdo, $id),
              'novo' => kdd_conceito_resumo($pdo, $novo)], 201);
}

/* ───────────────────────── Áreas ───────────────────────── */

/** POST /areas  { nome, parent_id? } */
function area_criar(array $auth): void
{
    kdd_exigir_validador($auth);
    $pdo  = kdd_db();
    $body = json_body();
    $nome = trim((string) ($body['nome'] ?? ''));
    $parent = isset($body['parent_id']) ? (int) $body['parent_id'] : null;
    if ($nome === '') {
        json_error('Informe o nome da área', 400);
    }
    if ($parent !== null) {
        $c = $pdo->prepare("SELECT id FROM area WHERE id = ?");
        $c->execute([$parent]);
        if (!$c->fetch()) {
            json_error('Área-pai não encontrada', 404);
        }
    }
    $pdo->prepare("INSERT INTO area (nome, parent_id) VALUES (?, ?)")->execute([$nome, $parent]);
    $aid = (int) $pdo->lastInsertId();
    kdd_log_changeset($pdo, $auth, 'criar_area', 'area', $aid, null, ['nome' => $nome, 'parent_id' => $parent]);
    json_out(['ok' => true, 'area' => ['id' => $aid, 'nome' => $nome, 'parent_id' => $parent]], 201);
}

/** PATCH /areas/{id}  { nome?, parent_id? }  (valida ciclo) */
function area_editar(array $auth, int $id): void
{
    kdd_exigir_validador($auth);
    $pdo  = kdd_db();
    $body = json_body();
    $s = $pdo->prepare("SELECT id, nome, parent_id FROM area WHERE id = ?");
    $s->execute([$id]);
    $old = $s->fetch();
    if (!$old) {
        json_error('Área não encontrada', 404);
    }
    if (isset($body['nome'])) {
        $nome = trim((string) $body['nome']);
        if ($nome === '') {
            json_error('nome não pode ficar vazio', 400);
        }
        $pdo->prepare("UPDATE area SET nome = ? WHERE id = ?")->execute([$nome, $id]);
    }
    if (array_key_exists('parent_id', $body)) {
        $parent = $body['parent_id'] === null ? null : (int) $body['parent_id'];
        if ($parent !== null) {
            if ($parent === $id || kdd_area_e_descendente($pdo, $parent, $id)) {
                json_error('parent_id criaria um ciclo na hierarquia', 400);
            }
        }
        $pdo->prepare("UPDATE area SET parent_id = ? WHERE id = ?")->execute([$parent, $id]);
    }
    kdd_log_changeset($pdo, $auth, 'editar_area', 'area', $id, $old, null);
    $s->execute([$id]);
    json_out(['ok' => true, 'area' => $s->fetch()]);
}

/** DELETE /areas/{id}  (bloqueia se tiver subáreas ou conceitos/fontes vinculados) */
function area_remover(array $auth, int $id): void
{
    kdd_exigir_validador($auth);
    $pdo = kdd_db();
    $s = $pdo->prepare("SELECT id, nome FROM area WHERE id = ?");
    $s->execute([$id]);
    $old = $s->fetch();
    if (!$old) {
        json_error('Área não encontrada', 404);
    }
    foreach ([
        ['SELECT COUNT(*) FROM area WHERE parent_id = ?', 'subáreas'],
        ['SELECT COUNT(*) FROM conceito_area WHERE area_id = ?', 'conceitos'],
        ['SELECT COUNT(*) FROM fonte_area WHERE area_id = ?', 'fontes'],
    ] as [$sql, $oque]) {
        $c = $pdo->prepare($sql);
        $c->execute([$id]);
        if ((int) $c->fetchColumn() > 0) {
            json_error("Área tem {$oque} vinculados; desvincule antes de remover", 409);
        }
    }
    $pdo->prepare("DELETE FROM area WHERE id = ?")->execute([$id]);
    kdd_log_changeset($pdo, $auth, 'remover_area', 'area', $id, $old, null);
    json_out(['ok' => true, 'area_removida' => $id]);
}

/** true se $candidato é descendente de $ancestral na hierarquia de áreas. */
function kdd_area_e_descendente(PDO $pdo, int $candidato, int $ancestral): bool
{
    $atual = $candidato;
    $guarda = 0;
    while ($atual !== null && $guarda++ < 1000) {
        $s = $pdo->prepare("SELECT parent_id FROM area WHERE id = ?");
        $s->execute([$atual]);
        $row = $s->fetch();
        if (!$row || $row['parent_id'] === null) {
            return false;
        }
        $atual = (int) $row['parent_id'];
        if ($atual === $ancestral) {
            return true;
        }
    }
    return false;
}
