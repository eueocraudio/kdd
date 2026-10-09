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
function kdd_fonte_curadoria(PDO $pdo, string $autor, int $universoId = 1): int
{
    $autor  = trim($autor) !== '' ? trim($autor) : 'curador';
    $titulo = 'Curadoria — ' . $autor;

    // ⚠️ UMA fonte de curadoria POR UNIVERSO. Se fosse uma só, a curadoria feita no
    // universo B apoiaria proposições do universo B numa fonte do universo A — a certeza
    // atravessaria a fronteira que é o ponto dos universos paralelos.
    $s = $pdo->prepare(
        "SELECT id FROM fonte WHERE origem = 'curadoria' AND titulo = ? AND universo_id = ? LIMIT 1"
    );
    $s->execute([$titulo, $universoId]);
    $row = $s->fetch();
    if ($row) {
        return (int) $row['id'];
    }
    $pdo->prepare(
        "INSERT INTO fonte (titulo, arquivo_caminho, origem, universo_id, status_proc, status_aprovacao)
         VALUES (?, NULL, 'curadoria', ?, 'processado', 'aprovada')"
    )->execute([$titulo, $universoId]);
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
    $s = $pdo->prepare(
        "SELECT id, sentido, tipo, desabilitado, universo_id, pais FROM conceito WHERE id = ?"
    );
    $s->execute([$id]);
    $c = $s->fetch();
    if (!$c) {
        return null;
    }
    $r = $pdo->prepare(
        "SELECT id, texto, idioma, principal FROM rotulo WHERE conceito_id = ?
          ORDER BY principal DESC, idioma, id"
    );
    $r->execute([$id]);
    $a = $pdo->prepare(
        "SELECT a.id, a.nome FROM conceito_area ca JOIN area a ON a.id = ca.area_id WHERE ca.conceito_id = ? ORDER BY a.nome"
    );
    $a->execute([$id]);
    return ['id' => (int) $c['id'], 'sentido' => $c['sentido'], 'tipo' => $c['tipo'],
            'desabilitado' => (int) $c['desabilitado'], 'pais' => $c['pais'],
            'universo' => kdd_universo_resumo($pdo, (int) $c['universo_id']),
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
    $pais    = kdd_pais_valido($body['pais'] ?? '');   // '' = vale em qualquer país
    // Curadoria pode informar o enquadramento (ou corrigir o que a IA leu) e a forma
    // inglesa da relação, que é o substrato da análise (docs/sentimento.md).
    $rel_en  = trim((string) ($body['relacao_en'] ?? ''));
    $polar   = kdd_polaridade_valida($body['polaridade'] ?? null);
    $subj    = kdd_subjetividade_valida($body['subjetividade'] ?? null);

    if ($origem <= 0 || $destino <= 0 || $relacao === '') {
        json_error('Informe origem_id, relacao e destino_id', 400);
    }
    kdd_assert_conceito($pdo, $origem);
    kdd_assert_conceito($pdo, $destino);

    // ⚠️ Proposição NUNCA cruza universo (docs/universos.md §3). É o que mantém cada
    // universo com sua própria verdade: certeza, valor e esteio só com o que existe ali.
    // Ligação entre universos não é proposição, é CONTRAPARTE (GET /conceitos/{id}/contrapartes).
    $uOrigem  = kdd_universo_do_conceito($pdo, $origem);
    $uDestino = kdd_universo_do_conceito($pdo, $destino);
    if ($uOrigem !== $uDestino) {
        json_error(
            'Proposição não pode cruzar universos: a origem está em ' .
            kdd_universo_resumo($pdo, $uOrigem)['slug'] . ' e o destino em ' .
            kdd_universo_resumo($pdo, $uDestino)['slug'] .
            '. Use as contrapartes para relacionar conceitos de universos diferentes.',
            409
        );
    }

    $pdo->beginTransaction();
    try {
        $prop_id  = kdd_upsert_proposicao($pdo, $origem, $relacao, $destino, $pais);
        $fonte_id = kdd_fonte_curadoria($pdo, (string) ($auth['descricao'] ?? ''), $uOrigem);

        if ($rel_en !== '') {
            $pdo->prepare("UPDATE proposicao SET relacao_en = ? WHERE id = ?")
                ->execute([$rel_en, $prop_id]);
        }
        $pdo->prepare(
            "INSERT INTO referencia (proposicao_id, fonte_id, polaridade, subjetividade)
             VALUES (?, ?, ?, ?)
             ON DUPLICATE KEY UPDATE polaridade = VALUES(polaridade),
                                     subjetividade = VALUES(subjetividade)"
        )->execute([$prop_id, $fonte_id, $polar, $subj]);
        foreach ([$origem, $destino] as $cid) {
            $pdo->prepare("INSERT IGNORE INTO conceito_fonte (conceito_id, fonte_id) VALUES (?, ?)")
                ->execute([$cid, $fonte_id]);
        }
        kdd_log_changeset($pdo, $auth, 'criar_proposicao', 'proposicao', $prop_id, null,
            ['origem_id' => $origem, 'relacao' => $relacao, 'destino_id' => $destino,
             'pais' => $pais, 'relacao_en' => $rel_en,
             'polaridade' => $polar, 'subjetividade' => $subj]);
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

    // Proposição nunca cruza universo (igual ao criar).
    $uOrigem  = kdd_universo_do_conceito($pdo, $origem);
    $uDestino = kdd_universo_do_conceito($pdo, $destino);
    if ($uOrigem !== $uDestino) {
        json_error('Proposição não pode cruzar universos', 409);
    }

    $pdo->beginTransaction();
    try {
        $novo_id  = kdd_upsert_proposicao($pdo, $origem, $relacao, $destino);
        $fonte_id = kdd_fonte_curadoria($pdo, (string) ($auth['descricao'] ?? ''), $uOrigem);

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

    $s = $pdo->prepare(
        "SELECT id, conceito_origem, relacao, conceito_destino, pais FROM proposicao WHERE id = ?"
    );
    $s->execute([$id]);
    $old = $s->fetch();
    if (!$old) {
        json_error('Proposição não encontrada', 404);
    }

    $pdo->beginTransaction();
    try {
        $fonte_id = kdd_fonte_curadoria(
            $pdo, (string) ($auth['descricao'] ?? ''),
            kdd_universo_do_conceito($pdo, (int) $old['conceito_origem'])
        );
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

/** Upsert idempotente de uma proposição (origem+relacao+destino+pais). Retorna o id.
 * O PAÍS entra na tripla (migration 009): a mesma relação pode valer num país e não noutro,
 * com certezas independentes. '' = universal. */
function kdd_upsert_proposicao(PDO $pdo, int $origem, string $relacao, int $destino,
                               string $pais = ''): int
{
    $pais = kdd_pais_valido($pais);
    $s = $pdo->prepare(
        "SELECT id FROM proposicao WHERE conceito_origem = ? AND relacao = ? AND conceito_destino = ?
            AND pais = ? LIMIT 1"
    );
    $s->execute([$origem, $relacao, $destino, $pais]);
    $row = $s->fetch();
    if ($row) {
        return (int) $row['id'];
    }
    $pdo->prepare(
        "INSERT INTO proposicao (conceito_origem, relacao, conceito_destino, pais)
         VALUES (?, ?, ?, ?)"
    )->execute([$origem, $relacao, $destino, $pais]);
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
function kdd_proposicao_view(PDO $pdo, int $id, string $idioma = ''): ?array
{
    $s = $pdo->prepare(
        "SELECT p.id, p.relacao, p.pais,
                p.conceito_origem  AS origem_id,
                p.conceito_destino AS destino_id,
                " . kdd_sql_rotulo('p.conceito_origem', $idioma) . " AS origem_rotulo,
                " . kdd_sql_rotulo('p.conceito_destino', $idioma) . " AS destino_rotulo
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

/** POST /conceitos  { sentido, rotulo_principal, areas?: [nomes], tipo?, universo?, pais?, idioma? } */
function conceito_criar(array $auth): void
{
    kdd_exigir_validador($auth);
    $pdo  = kdd_db();
    $body = json_body();

    $sentido = trim((string) ($body['sentido'] ?? ''));
    $rotulo  = trim((string) ($body['rotulo_principal'] ?? ''));
    $areas   = is_array($body['areas'] ?? null) ? $body['areas'] : [];
    $tipo    = kdd_tipo_valido($body['tipo'] ?? null);
    $uid     = kdd_universo_req($pdo, $body['universo'] ?? null);
    $pais    = kdd_pais_valido($body['pais'] ?? '');          // '' = universal
    $idioma  = kdd_idioma_valido($body['idioma'] ?? '') ?: KDD_IDIOMA_PADRAO;
    if ($sentido === '' || $rotulo === '') {
        json_error('Informe sentido e rotulo_principal', 400);
    }

    // Unicidade do sentido é por (universo, pais) — migrations 008 e 009.
    $s = $pdo->prepare(
        "SELECT id FROM conceito WHERE universo_id = ? AND pais = ? AND sentido = ? LIMIT 1"
    );
    $s->execute([$uid, $pais, $sentido]);
    if ($s->fetch()) {
        json_error('Já existe um conceito com esse sentido neste universo e país', 409);
    }

    $pdo->beginTransaction();
    try {
        $pdo->prepare("INSERT INTO conceito (sentido, tipo, universo_id, pais) VALUES (?, ?, ?, ?)")
            ->execute([$sentido, $tipo, $uid, $pais]);
        $cid = (int) $pdo->lastInsertId();
        kdd_garantir_rotulo($pdo, $cid, $rotulo, true, $idioma);
        foreach ($areas as $nome) {
            $nome = trim((string) $nome);
            if ($nome === '') { continue; }
            $aid = kdd_upsert_area($pdo, $nome, $uid);
            $pdo->prepare("INSERT IGNORE INTO conceito_area (conceito_id, area_id) VALUES (?, ?)")
                ->execute([$cid, $aid]);
        }
        $fonte_id = kdd_fonte_curadoria($pdo, (string) ($auth['descricao'] ?? ''), $uid);
        $pdo->prepare("INSERT IGNORE INTO conceito_fonte (conceito_id, fonte_id) VALUES (?, ?)")
            ->execute([$cid, $fonte_id]);
        kdd_log_changeset($pdo, $auth, 'criar_conceito', 'conceito', $cid, null,
            ['sentido' => $sentido, 'tipo' => $tipo, 'rotulo_principal' => $rotulo,
             'areas' => $areas, 'universo_id' => $uid, 'pais' => $pais, 'idioma' => $idioma]);
        $pdo->commit();
    } catch (Throwable $e) {
        $pdo->rollBack();
        json_erro_interno($e, 'criar conceito');
    }

    json_out(['ok' => true, 'conceito' => kdd_conceito_resumo($pdo, $cid)], 201);
}

/** PATCH /conceitos/{id}  { sentido?, tipo? } — tipo: entidade|classe|processo|atributo|outro
 * (entra no cálculo do valor; '' ou null limpa). */
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
    if (array_key_exists('tipo', $body)) {
        // Curadoria manda no tipo: o bot só preenche quando está NULL (ver fontes_mapas).
        $pdo->prepare("UPDATE conceito SET tipo = ? WHERE id = ?")
            ->execute([kdd_tipo_valido($body['tipo']), $id]);
    }
    kdd_log_changeset($pdo, $auth, 'editar_conceito', 'conceito', $id, $antes, kdd_conceito_resumo($pdo, $id));
    json_out(['ok' => true, 'conceito' => kdd_conceito_resumo($pdo, $id)]);
}

/** POST /conceitos/{id}/desabilitar  { desabilitado: 0|1 }
 * Desabilita/reabilita um conceito. As PROPOSIÇÕES que o envolvem ficam inativas por
 * cálculo (o mapa marca; nada é apagado; reabilitar reverte). */
function conceito_desabilitar(array $auth, int $id): void
{
    kdd_exigir_validador($auth);
    $pdo  = kdd_db();
    $body = json_body();
    kdd_assert_conceito($pdo, $id);
    if (!isset($body['desabilitado']) || !in_array((int) $body['desabilitado'], [0, 1], true)) {
        json_error('Informe desabilitado: 0 ou 1', 400);
    }
    $des   = (int) $body['desabilitado'];
    $antes = kdd_conceito_resumo($pdo, $id);
    $pdo->prepare("UPDATE conceito SET desabilitado = ? WHERE id = ?")->execute([$des, $id]);
    $depois = kdd_conceito_resumo($pdo, $id);
    kdd_log_changeset($pdo, $auth, $des ? 'desabilitar_conceito' : 'reabilitar_conceito',
                      'conceito', $id, $antes, $depois);
    json_out(['ok' => true, 'conceito' => $depois]);
}

/** POST /conceitos/{id}/rotulos  { texto, idioma?, principal? }
 * É por aqui que se TRADUZ um conceito: mesmo conceito, rótulo em outro idioma
 * (docs/idioma-pais.md §3). O idioma entra na unicidade do rótulo. */
function conceito_add_rotulo(array $auth, int $id): void
{
    kdd_exigir_validador($auth);
    $pdo  = kdd_db();
    $body = json_body();
    kdd_assert_conceito($pdo, $id);

    $texto     = trim((string) ($body['texto'] ?? ''));
    $principal = (bool) ($body['principal'] ?? false);
    $idioma    = kdd_idioma_valido($body['idioma'] ?? '') ?: KDD_IDIOMA_PADRAO;
    if ($texto === '') {
        json_error('Informe o texto do rótulo', 400);
    }
    if ($principal) {
        $pdo->prepare("UPDATE rotulo SET principal = 0 WHERE conceito_id = ?")->execute([$id]);
    }
    kdd_garantir_rotulo($pdo, $id, $texto, $principal, $idioma);
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
        // Área criada aqui nasce no universo DO CONCEITO.
        $aid = kdd_upsert_area($pdo, $nome, kdd_universo_do_conceito($pdo, $id));
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

    // ⚠️ Fusão entre universos é PROIBIDA (docs/universos.md §5): fundir destruiria o
    // isolamento que é o ponto da coisa. Dois conceitos "iguais" em universos diferentes
    // são CONTRAPARTES, não duplicatas.
    // Merge entre PAÍSES também é proibido: "Imposto de Renda" (BR) e o equivalente
    // português não são duplicatas, são institutos distintos (docs/idioma-pais.md §2).
    $pq = $pdo->prepare("SELECT pais FROM conceito WHERE id = ?");
    $pq->execute([$id]);      $pAlvo  = (string) ($pq->fetchColumn() ?: '');
    $pq->execute([$outro]);   $pOutro = (string) ($pq->fetchColumn() ?: '');
    if ($pAlvo !== $pOutro) {
        json_error(
            "Não se funde conceito de países diferentes ('" . ($pAlvo ?: 'universal') .
            "' x '" . ($pOutro ?: 'universal') . "'). São institutos distintos, não duplicatas.",
            409
        );
    }

    $uAlvo  = kdd_universo_do_conceito($pdo, $id);
    $uOutro = kdd_universo_do_conceito($pdo, $outro);
    if ($uAlvo !== $uOutro) {
        json_error(
            'Não se funde conceito de universos diferentes (' .
            kdd_universo_resumo($pdo, $uAlvo)['slug'] . ' x ' .
            kdd_universo_resumo($pdo, $uOutro)['slug'] .
            '). Eles são contrapartes, não duplicatas.',
            409
        );
    }

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
    // O conceito novo HERDA universo E país do original (um split não atravessa fronteira).
    $uid = kdd_universo_do_conceito($pdo, $id);
    $sp  = $pdo->prepare("SELECT pais FROM conceito WHERE id = ?");
    $sp->execute([$id]);
    $pais_orig = (string) ($sp->fetchColumn() ?: '');
    $s = $pdo->prepare(
        "SELECT id FROM conceito WHERE universo_id = ? AND pais = ? AND sentido = ? LIMIT 1"
    );
    $s->execute([$uid, $pais_orig, $sentido]);
    if ($s->fetch()) {
        json_error('Já existe um conceito com esse sentido neste universo e país', 409);
    }
    $rotulo_ids = array_map('intval', is_array($body['rotulo_ids'] ?? null) ? $body['rotulo_ids'] : []);
    $prop_ids   = array_map('intval', is_array($body['proposicao_ids'] ?? null) ? $body['proposicao_ids'] : []);
    $rot_princ  = trim((string) ($body['rotulo_principal'] ?? ''));

    $pdo->beginTransaction();
    try {
        $pdo->prepare("INSERT INTO conceito (sentido, universo_id, pais) VALUES (?, ?, ?)")
            ->execute([$sentido, $uid, $pais_orig]);
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
        $fonte_id = kdd_fonte_curadoria($pdo, (string) ($auth['descricao'] ?? ''), $uid);
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
    $uid  = kdd_universo_req($pdo, $body['universo'] ?? null);
    if ($nome === '') {
        json_error('Informe o nome da área', 400);
    }
    if ($parent !== null) {
        // A hierarquia de áreas não cruza universo: a mãe tem que ser do mesmo.
        $c = $pdo->prepare("SELECT id, universo_id FROM area WHERE id = ?");
        $c->execute([$parent]);
        $pai = $c->fetch();
        if (!$pai) {
            json_error('Área-pai não encontrada', 404);
        }
        if ((int) $pai['universo_id'] !== $uid) {
            json_error('A área-pai está em outro universo', 409);
        }
    }
    $pdo->prepare("INSERT INTO area (nome, parent_id, universo_id) VALUES (?, ?, ?)")
        ->execute([$nome, $parent, $uid]);
    $aid = (int) $pdo->lastInsertId();
    kdd_log_changeset($pdo, $auth, 'criar_area', 'area', $aid, null,
        ['nome' => $nome, 'parent_id' => $parent, 'universo_id' => $uid]);
    json_out(['ok' => true, 'area' => ['id' => $aid, 'nome' => $nome, 'parent_id' => $parent,
                                       'universo' => kdd_universo_resumo($pdo, $uid)]], 201);
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
