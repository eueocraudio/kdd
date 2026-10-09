<?php
declare(strict_types=1);

/**
 * UNIVERSOS PARALELOS (docs/universos.md).
 *
 * ⚠️ A identidade do conceito é `(universo_id, sentido)`, não só `sentido` — inversão
 * deliberada da decisão original, documentada na spec §2. Dentro de um universo nada muda:
 * identidade = sentido, e área segue sendo dimensão N–N sem poder de identidade.
 *
 * Resolução em toda requisição: `?universo=<slug|id>` na leitura, campo `universo` no corpo
 * na escrita. Ausente ⇒ `principal` (id 1) — é o que mantém o desktop e o bot atuais
 * funcionando sem alteração nenhuma.
 */

const KDD_UNIVERSO_PADRAO = 'principal';

/** Busca um universo por slug OU id numérico. Null se não existir. */
function kdd_universo_buscar(PDO $pdo, string $valor): ?array
{
    $valor = trim($valor);
    if ($valor === '') {
        return null;
    }
    if (ctype_digit($valor)) {
        $s = $pdo->prepare("SELECT id, slug, nome, descricao FROM universo WHERE id = ? LIMIT 1");
        $s->execute([(int) $valor]);
    } else {
        $s = $pdo->prepare("SELECT id, slug, nome, descricao FROM universo WHERE slug = ? LIMIT 1");
        $s->execute([$valor]);
    }
    $row = $s->fetch();
    return $row ?: null;
}

/**
 * Id do universo desta requisição. Ordem: $explicito (corpo de escrita) → ?universo= →
 * padrão. Universo desconhecido devolve 404, nunca cai no padrão em silêncio — senão uma
 * escrita com slug errado contaminaria o universo principal.
 */
function kdd_universo_req(PDO $pdo, $explicito = null): int
{
    $valor = '';
    if ($explicito !== null && trim((string) $explicito) !== '') {
        $valor = (string) $explicito;
    } elseif (isset($_GET['universo']) && trim((string) $_GET['universo']) !== '') {
        $valor = (string) $_GET['universo'];
    }

    if ($valor === '') {
        $u = kdd_universo_buscar($pdo, KDD_UNIVERSO_PADRAO);
        if (!$u) {
            json_error("Universo padrão '" . KDD_UNIVERSO_PADRAO . "' não existe. Rode as migrations.", 500);
        }
        return (int) $u['id'];
    }

    $u = kdd_universo_buscar($pdo, $valor);
    if (!$u) {
        json_error("Universo não encontrado: " . $valor, 404);
    }
    return (int) $u['id'];
}

/** Universo de um conceito (0 se não existir). */
function kdd_universo_do_conceito(PDO $pdo, int $conceitoId): int
{
    $s = $pdo->prepare("SELECT universo_id FROM conceito WHERE id = ?");
    $s->execute([$conceitoId]);
    return (int) ($s->fetchColumn() ?: 0);
}

/** Universo de uma fonte (0 se não existir). */
function kdd_universo_da_fonte(PDO $pdo, int $fonteId): int
{
    $s = $pdo->prepare("SELECT universo_id FROM fonte WHERE id = ?");
    $s->execute([$fonteId]);
    return (int) ($s->fetchColumn() ?: 0);
}

/** Resumo {id, slug, nome} de um universo, para anexar numa resposta. */
function kdd_universo_resumo(PDO $pdo, int $id): array
{
    $s = $pdo->prepare("SELECT id, slug, nome, idioma FROM universo WHERE id = ?");
    $s->execute([$id]);
    $u = $s->fetch() ?: ['id' => $id, 'slug' => null, 'nome' => null, 'idioma' => null];
    return ['id' => (int) $u['id'], 'slug' => $u['slug'], 'nome' => $u['nome'],
            'idioma' => $u['idioma']];
}

/* ───────────────────────── Endpoints ───────────────────────── */

/** GET /universos — todos os universos, com o que cada um contém. */
function universos_listar(): void
{
    $pdo = kdd_db();
    $rows = $pdo->query(
        "SELECT u.id, u.slug, u.nome, u.descricao, u.idioma, u.criado_em,
                (SELECT COUNT(*) FROM conceito c WHERE c.universo_id = u.id) AS conceitos,
                (SELECT COUNT(*) FROM area    a WHERE a.universo_id = u.id) AS areas,
                (SELECT COUNT(*) FROM fonte   f WHERE f.universo_id = u.id) AS fontes
           FROM universo u ORDER BY u.id"
    )->fetchAll();

    $universos = array_map(static function (array $u): array {
        return [
            'id' => (int) $u['id'], 'slug' => $u['slug'], 'nome' => $u['nome'],
            'descricao' => $u['descricao'], 'idioma' => $u['idioma'],
            'criado_em' => $u['criado_em'],
            'conceitos' => (int) $u['conceitos'], 'areas' => (int) $u['areas'],
            'fontes' => (int) $u['fontes'],
        ];
    }, $rows);

    json_out(['universos' => $universos, 'padrao' => KDD_UNIVERSO_PADRAO]);
}

/** POST /universos  { slug, nome, descricao? } — exige validador. */
function universo_criar(array $auth): void
{
    kdd_exigir_validador($auth);
    $pdo  = kdd_db();
    $body = json_body();

    $slug = mb_strtolower(trim((string) ($body['slug'] ?? '')));
    $nome = trim((string) ($body['nome'] ?? ''));
    $desc = trim((string) ($body['descricao'] ?? ''));
    // idioma-BASE do universo: a língua em que os SENTIDOS dele são escritos
    // (docs/idioma-pais.md §3). Rótulos podem estar em qualquer idioma.
    $idioma = kdd_idioma_valido($body['idioma'] ?? '') ?: KDD_IDIOMA_PADRAO;

    if ($slug === '' || $nome === '') {
        json_error('Informe slug e nome', 400);
    }
    // slug é identificador de URL: só minúsculas, dígitos, hífen e sublinhado.
    if (!preg_match('/^[a-z0-9][a-z0-9_-]{1,63}$/', $slug)) {
        json_error('slug inválido: use 2 a 64 caracteres [a-z0-9_-], começando por letra ou dígito', 400);
    }
    if (kdd_universo_buscar($pdo, $slug)) {
        json_error('Já existe um universo com esse slug', 409);
    }

    $pdo->prepare("INSERT INTO universo (slug, nome, descricao, idioma) VALUES (?, ?, ?, ?)")
        ->execute([$slug, $nome, $desc !== '' ? $desc : null, $idioma]);
    $uid = (int) $pdo->lastInsertId();

    kdd_log_changeset($pdo, $auth, 'criar_universo', 'universo', $uid, null,
        ['slug' => $slug, 'nome' => $nome, 'descricao' => $desc, 'idioma' => $idioma]);

    json_out(['ok' => true, 'universo' => kdd_universo_resumo($pdo, $uid)], 201);
}

/**
 * GET /conceitos/{id}/contrapartes — o mesmo conceito nos OUTROS universos (spec §5).
 *
 * É o que torna os universos "paralelos" em vez de só isolados. Duas pontes, nenhuma delas
 * proposição (proposição nunca cruza universo):
 *   1. por RÓTULO — mesmo texto de rótulo, comparado sem caixa;
 *   2. por VETOR  — par de `conceito_similar` cujos lados estão em universos diferentes.
 *      O cálculo é o mesmo da fila de merge; só a leitura muda (lá é duplicata, aqui é gêmeo).
 */
function conceito_contrapartes(int $id): void
{
    $pdo    = kdd_db();
    $idioma = kdd_idioma_req();
    $s = $pdo->prepare("SELECT id, sentido, universo_id, pais FROM conceito WHERE id = ?");
    $s->execute([$id]);
    $base = $s->fetch();
    if (!$base) {
        json_error('Conceito não encontrado', 404);
    }
    $universoBase = (int) $base['universo_id'];

    // 1. por rótulo
    $s = $pdo->prepare(
        "SELECT DISTINCT c.id, c.sentido, c.tipo, c.universo_id, c.pais, r2.texto AS rotulo_casado,
                " . kdd_sql_rotulo('c.id', $idioma) . " AS rotulo
           FROM rotulo r1
           JOIN rotulo r2 ON LOWER(r2.texto) = LOWER(r1.texto) AND r2.conceito_id <> r1.conceito_id
           JOIN conceito c ON c.id = r2.conceito_id
          WHERE r1.conceito_id = ? AND c.universo_id <> ?
          ORDER BY c.universo_id, c.id"
    );
    $s->execute([$id, $universoBase]);
    $porRotulo = [];
    foreach ($s->fetchAll() as $r) {
        $porRotulo[] = [
            'id' => (int) $r['id'], 'rotulo' => $r['rotulo'], 'sentido' => $r['sentido'],
            'tipo' => $r['tipo'], 'pais' => $r['pais'],
            'universo' => kdd_universo_resumo($pdo, (int) $r['universo_id']),
            'casamento' => 'rotulo', 'rotulo_casado' => $r['rotulo_casado'], 'similaridade' => null,
        ];
    }

    // 2. por vetor
    $s = $pdo->prepare(
        "SELECT IF(s.conceito_a = ?, s.conceito_b, s.conceito_a) AS outro_id, s.similaridade, s.modelo
           FROM conceito_similar s
          WHERE (s.conceito_a = ? OR s.conceito_b = ?)
          ORDER BY s.similaridade DESC"
    );
    $s->execute([$id, $id, $id]);
    $porVetor = [];
    foreach ($s->fetchAll() as $r) {
        $outro = (int) $r['outro_id'];
        $q = $pdo->prepare(
            "SELECT c.id, c.sentido, c.tipo, c.universo_id, c.pais,
                    " . kdd_sql_rotulo('c.id', $idioma) . " AS rotulo
               FROM conceito c WHERE c.id = ? AND c.universo_id <> ?"
        );
        $q->execute([$outro, $universoBase]);
        $c = $q->fetch();
        if (!$c) {
            continue;   // mesmo universo: é candidato a MERGE, não contraparte
        }
        $porVetor[] = [
            'id' => (int) $c['id'], 'rotulo' => $c['rotulo'], 'sentido' => $c['sentido'],
            'tipo' => $c['tipo'], 'pais' => $c['pais'],
            'universo' => kdd_universo_resumo($pdo, (int) $c['universo_id']),
            'casamento' => 'vetor', 'rotulo_casado' => null,
            'similaridade' => (float) $r['similaridade'], 'modelo' => $r['modelo'],
        ];
    }

    json_out([
        'conceito' => [
            'id' => (int) $base['id'], 'sentido' => $base['sentido'], 'pais' => $base['pais'],
            'universo' => kdd_universo_resumo($pdo, $universoBase),
        ],
        'contrapartes' => array_merge($porRotulo, $porVetor),
        'por_rotulo' => count($porRotulo),
        'por_vetor'  => count($porVetor),
    ]);
}
