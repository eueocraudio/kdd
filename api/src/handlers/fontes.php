<?php
declare(strict_types=1);

/** Diretório absoluto onde os PDFs são guardados. */
function kdd_pdf_dir(): string
{
    $d = env('PDF_STORAGE_PATH', 'storage/pdfs');
    if ($d === '' || $d[0] !== '/') {
        $d = APP_ROOT . '/' . $d;
    }
    return $d;
}

/** GET /fontes  (opcional ?status_proc=pendente) */
function fontes_listar(): void
{
    $pdo = kdd_db();
    $status = $_GET['status_proc'] ?? null;

    if ($status !== null && $status !== '') {
        $stmt = $pdo->prepare(
            "SELECT id, titulo, status_proc, status_aprovacao, criado_em
               FROM fonte WHERE status_proc = ? ORDER BY id DESC"
        );
        $stmt->execute([$status]);
    } else {
        $stmt = $pdo->query(
            "SELECT id, titulo, status_proc, status_aprovacao, criado_em
               FROM fonte ORDER BY id DESC"
        );
    }

    json_out(['fontes' => $stmt->fetchAll()]);
}

/** GET /fontes/{id} */
function fontes_obter(int $id): void
{
    $pdo = kdd_db();
    $stmt = $pdo->prepare(
        "SELECT f.id, f.titulo, f.arquivo_caminho, f.status_proc, f.status_aprovacao,
                f.enviado_por, f.criado_em,
                GROUP_CONCAT(a.nome ORDER BY a.id SEPARATOR ', ') AS areas
           FROM fonte f
           LEFT JOIN fonte_area fa ON fa.fonte_id = f.id
           LEFT JOIN area a ON a.id = fa.area_id
          WHERE f.id = ?
          GROUP BY f.id"
    );
    $stmt->execute([$id]);
    $f = $stmt->fetch();
    if (!$f) {
        json_error('Fonte não encontrada', 404);
    }
    json_out(['fonte' => $f]);
}

/** POST /fontes  (multipart/form-data: arquivo=<pdf>, titulo opcional) */
function fontes_criar(array $auth): void
{
    if (!isset($_FILES['arquivo']) || $_FILES['arquivo']['error'] !== UPLOAD_ERR_OK) {
        json_error('Envie o PDF no campo "arquivo" (multipart/form-data)', 400);
    }

    $file = $_FILES['arquivo'];
    $orig = (string) $file['name'];
    $ext  = strtolower(pathinfo($orig, PATHINFO_EXTENSION));
    if (!in_array($ext, ['pdf', 'txt'], true)) {
        json_error('Apenas arquivos .pdf ou .txt', 415);
    }

    // Dedup por conteúdo: hash do arquivo. Se já existe uma fonte com o mesmo
    // hash, não reenvia nem reprocessa — devolve a fonte existente (409).
    $hash = hash_file('sha256', $file['tmp_name']);
    $pdo  = kdd_db();
    $dup  = $pdo->prepare("SELECT id, titulo, status_proc, status_aprovacao FROM fonte WHERE arquivo_hash = ? LIMIT 1");
    $dup->execute([$hash]);
    if ($existente = $dup->fetch()) {
        json_out([
            'erro'      => 'PDF já enviado anteriormente (mesmo conteúdo); não será reprocessado.',
            'duplicado' => true,
            'fonte'     => [
                'id'               => (int) $existente['id'],
                'titulo'           => $existente['titulo'],
                'status_proc'      => $existente['status_proc'],
                'status_aprovacao' => $existente['status_aprovacao'],
            ],
        ], 409);
    }

    $dir = kdd_pdf_dir();
    if (!is_dir($dir) && !@mkdir($dir, 0775, true) && !is_dir($dir)) {
        json_error('Não foi possível criar o diretório de storage', 500);
    }

    $nome    = date('Ymd_His') . '_' . bin2hex(random_bytes(6)) . '.' . $ext;
    $destino = $dir . '/' . $nome;
    if (!move_uploaded_file($file['tmp_name'], $destino)) {
        json_error('Falha ao salvar o arquivo', 500);
    }

    $titulo = trim((string) ($_POST['titulo'] ?? '')) ?: pathinfo($orig, PATHINFO_FILENAME);

    $stmt = $pdo->prepare(
        "INSERT INTO fonte (titulo, arquivo_caminho, arquivo_hash, status_proc, status_aprovacao)
         VALUES (?, ?, ?, 'pendente', 'pendente')"
    );
    $stmt->execute([$titulo, $nome, $hash]);
    $id = (int) $pdo->lastInsertId();

    json_out([
        'fonte' => [
            'id'               => $id,
            'titulo'           => $titulo,
            'status_proc'      => 'pendente',
            'status_aprovacao' => 'pendente',
        ],
    ], 201);
}

/** GET /fontes/{id}/arquivo  (download do PDF — usado pelo bot) */
function fontes_baixar(int $id): void
{
    $pdo = kdd_db();
    $stmt = $pdo->prepare("SELECT arquivo_caminho FROM fonte WHERE id = ?");
    $stmt->execute([$id]);
    $f = $stmt->fetch();
    if (!$f) {
        json_error('Fonte não encontrada', 404);
    }

    $caminho = kdd_pdf_dir() . '/' . $f['arquivo_caminho'];
    if (!is_file($caminho)) {
        json_error('Arquivo não encontrado no storage', 404);
    }

    $ext = strtolower(pathinfo($f['arquivo_caminho'], PATHINFO_EXTENSION)) ?: 'pdf';
    $tipo = $ext === 'txt' ? 'text/plain; charset=utf-8' : 'application/pdf';
    header('Content-Type: ' . $tipo);
    header('Content-Disposition: attachment; filename="fonte_' . $id . '.' . $ext . '"');
    header('Content-Length: ' . filesize($caminho));
    readfile($caminho);
    exit;
}

/**
 * PATCH /fontes/{id}
 * Bot usa para atualizar status_proc e/ou gravar áreas inferidas.
 * Corpo JSON: { "status_proc": "processando"|"processado"|"erro", "areas": ["Futebol", "Jornalismo"] }
 * "areas" são nomes; cria a área se não existir.
 */
function fontes_atualizar(int $id): void
{
    $pdo  = kdd_db();
    $body = json_body();

    // Verifica existência
    $stmt = $pdo->prepare("SELECT id FROM fonte WHERE id = ?");
    $stmt->execute([$id]);
    if (!$stmt->fetch()) {
        json_error('Fonte não encontrada', 404);
    }

    // Atualiza status_proc se fornecido
    $status_validos = ['processando', 'processado', 'erro'];
    if (isset($body['status_proc'])) {
        if (!in_array($body['status_proc'], $status_validos, true)) {
            json_error('status_proc inválido. Valores aceitos: ' . implode(', ', $status_validos), 400);
        }
        $pdo->prepare("UPDATE fonte SET status_proc = ? WHERE id = ?")
            ->execute([$body['status_proc'], $id]);
    }

    // Vincula áreas se fornecidas (cria as que não existirem)
    if (isset($body['areas']) && is_array($body['areas'])) {
        $areas_gravadas = [];
        foreach ($body['areas'] as $nome_area) {
            $nome_area = trim((string) $nome_area);
            if ($nome_area === '') {
                continue;
            }
            $area_id = kdd_upsert_area($pdo, $nome_area);

            // Vínculo N–N fonte_area (ignora duplicado)
            $pdo->prepare(
                "INSERT IGNORE INTO fonte_area (fonte_id, area_id) VALUES (?, ?)"
            )->execute([$id, $area_id]);

            $areas_gravadas[] = ['id' => $area_id, 'nome' => $nome_area];
        }
    }

    // Devolve fonte atualizada
    $stmt = $pdo->prepare("SELECT id, titulo, status_proc, status_aprovacao FROM fonte WHERE id = ?");
    $stmt->execute([$id]);
    json_out(['fonte' => $stmt->fetch()]);
}

/**
 * POST /fontes/{id}/mapas
 * Bot empurra o mapa extraído do PDF em uma única transação.
 *
 * Corpo JSON:
 * {
 *   "conceitos": [
 *     { "rotulo": "Botafogo", "sentido": "Time de futebol carioca", "areas": ["Futebol"] }
 *   ],
 *   "proposicoes": [
 *     { "origem_rotulo": "Botafogo", "relacao": "fundado_em", "destino_rotulo": "1894",
 *       "destino_sentido": "Ano de fundação do Botafogo" }
 *   ]
 * }
 *
 * Desambiguação: (rotulo + area) → conceito existente; cria se não encontrar.
 */
function fontes_mapas(int $id): void
{
    $pdo  = kdd_db();
    $body = json_body();

    // Verifica existência e status
    $stmt = $pdo->prepare("SELECT id, status_proc FROM fonte WHERE id = ?");
    $stmt->execute([$id]);
    $fonte = $stmt->fetch();
    if (!$fonte) {
        json_error('Fonte não encontrada', 404);
    }

    $conceitos_raw   = $body['conceitos']   ?? [];
    $proposicoes_raw = $body['proposicoes'] ?? [];

    if (!is_array($conceitos_raw) || !is_array($proposicoes_raw)) {
        json_error('Corpo inválido: esperado { conceitos: [...], proposicoes: [...] }', 400);
    }

    $pdo->beginTransaction();
    try {
        // ── 1. Upsert de conceitos; monta mapa rotulo→conceito_id ──
        $mapa_rotulo   = [];   // rotulo (minusc.) → conceito_id (namespace do push)
        $ids_conceitos = [];   // set de conceito_id distintos tocados (p/ contagem)

        foreach ($conceitos_raw as $c) {
            $rotulo  = trim((string) ($c['rotulo']  ?? ''));
            $sentido = trim((string) ($c['sentido'] ?? $rotulo));
            $areas   = is_array($c['areas'] ?? null) ? $c['areas'] : [];

            if ($rotulo === '') {
                continue;
            }

            // Identidade no nível do SENTIDO (Novak/spec): reaproveita o conceito de
            // mesmo sentido; senão cria. NÃO funde homônimos — mesmo rótulo com
            // sentidos distintos = conceitos distintos. A área é dimensão N–N de
            // classificação, não critério de identidade.
            $conceito_id = kdd_resolver_conceito($pdo, $rotulo, $sentido);

            // Vincula conceito às áreas e à fonte
            foreach ($areas as $nome_area) {
                $nome_area = trim((string) $nome_area);
                if ($nome_area === '') {
                    continue;
                }
                $area_id = kdd_upsert_area($pdo, $nome_area);
                $pdo->prepare(
                    "INSERT IGNORE INTO conceito_area (conceito_id, area_id) VALUES (?, ?)"
                )->execute([$conceito_id, $area_id]);
                $pdo->prepare(
                    "INSERT IGNORE INTO fonte_area (fonte_id, area_id) VALUES (?, ?)"
                )->execute([$id, $area_id]);
            }

            $pdo->prepare(
                "INSERT IGNORE INTO conceito_fonte (conceito_id, fonte_id) VALUES (?, ?)"
            )->execute([$conceito_id, $id]);

            $mapa_rotulo[mb_strtolower($rotulo)] = $conceito_id;
            $ids_conceitos[$conceito_id] = true;
        }

        // ── 2. Proposições + referências ──
        $props_criadas = 0;
        foreach ($proposicoes_raw as $p) {
            $orig_rotulo    = mb_strtolower(trim((string) ($p['origem_rotulo']    ?? '')));
            $dest_rotulo    = mb_strtolower(trim((string) ($p['destino_rotulo']   ?? '')));
            $dest_sentido   = trim((string) ($p['destino_sentido'] ?? $p['destino_rotulo'] ?? ''));
            $relacao        = trim((string) ($p['relacao']         ?? ''));

            if ($orig_rotulo === '' || $dest_rotulo === '' || $relacao === '') {
                continue;
            }

            $orig_id = $mapa_rotulo[$orig_rotulo] ?? null;
            $dest_id = $mapa_rotulo[$dest_rotulo] ?? null;

            // Resolve o conceito destino (caso não venha no array "conceitos").
            // Mesma regra de identidade por SENTIDO; destino_sentido cai para o
            // destino_rotulo quando o bot não informa o sentido (idempotente).
            if ($dest_id === null && $dest_sentido !== '') {
                $dest_rotulo_orig = trim((string) ($p['destino_rotulo'] ?? ''));
                $dest_id = kdd_resolver_conceito($pdo, $dest_rotulo_orig, $dest_sentido);
                $mapa_rotulo[$dest_rotulo] = $dest_id;
                $ids_conceitos[$dest_id] = true;
                // proveniência: esta fonte introduziu/usou o conceito destino
                $pdo->prepare(
                    "INSERT IGNORE INTO conceito_fonte (conceito_id, fonte_id) VALUES (?, ?)"
                )->execute([$dest_id, $id]);
            }

            if ($orig_id === null || $dest_id === null) {
                continue;
            }

            // Upsert proposição (idempotente por origem+relação+destino)
            $s = $pdo->prepare(
                "SELECT id FROM proposicao
                  WHERE conceito_origem = ? AND relacao = ? AND conceito_destino = ? LIMIT 1"
            );
            $s->execute([$orig_id, $relacao, $dest_id]);
            $prop = $s->fetch();

            if ($prop) {
                $prop_id = (int) $prop['id'];
            } else {
                $pdo->prepare(
                    "INSERT INTO proposicao (conceito_origem, relacao, conceito_destino)
                     VALUES (?, ?, ?)"
                )->execute([$orig_id, $relacao, $dest_id]);
                $prop_id = (int) $pdo->lastInsertId();
                $props_criadas++;
            }

            // Referência: esta fonte sustenta esta proposição
            $pdo->prepare(
                "INSERT IGNORE INTO referencia (proposicao_id, fonte_id) VALUES (?, ?)"
            )->execute([$prop_id, $id]);
        }

        // Marca fonte como processada
        $pdo->prepare("UPDATE fonte SET status_proc = 'processado' WHERE id = ?")
            ->execute([$id]);

        $pdo->commit();

        json_out([
            'ok'             => true,
            'conceitos'      => count($ids_conceitos),
            'proposicoes'    => $props_criadas,
            'fonte_id'       => $id,
            'status_proc'    => 'processado',
        ]);
    } catch (Throwable $e) {
        $pdo->rollBack();
        json_error('Falha na transação: ' . $e->getMessage(), 500);
    }
}

/**
 * Resolve um conceito pela sua IDENTIDADE = o SENTIDO (alinhado a Novak/spec).
 * Reaproveita o conceito de mesmo sentido (garantindo que o rótulo exista nele);
 * senão cria um conceito novo com esse rótulo como principal.
 *
 * Consequência intencional: rótulos iguais com sentidos diferentes geram conceitos
 * diferentes (homônimos preservados — ex.: Botafogo-time × Botafogo-bairro).
 */
function kdd_resolver_conceito(PDO $pdo, string $rotulo, string $sentido): int
{
    $sentido = trim($sentido) !== '' ? trim($sentido) : trim($rotulo);

    $s = $pdo->prepare("SELECT id FROM conceito WHERE sentido = ? LIMIT 1");
    $s->execute([$sentido]);
    $row = $s->fetch();

    if ($row) {
        $conceito_id = (int) $row['id'];
        kdd_garantir_rotulo($pdo, $conceito_id, $rotulo, false);
        return $conceito_id;
    }

    $pdo->prepare("INSERT INTO conceito (sentido) VALUES (?)")->execute([$sentido]);
    $conceito_id = (int) $pdo->lastInsertId();
    kdd_garantir_rotulo($pdo, $conceito_id, $rotulo, true);
    return $conceito_id;
}

/**
 * Garante que o conceito tenha o rótulo dado (sem duplicar). Marca como principal
 * apenas quando solicitado (tipicamente no rótulo de criação do conceito).
 */
function kdd_garantir_rotulo(PDO $pdo, int $conceitoId, string $rotulo, bool $principal): void
{
    $rotulo = trim($rotulo);
    if ($rotulo === '') {
        return;
    }
    $s = $pdo->prepare("SELECT id FROM rotulo WHERE conceito_id = ? AND texto = ? LIMIT 1");
    $s->execute([$conceitoId, $rotulo]);
    if ($s->fetch()) {
        return;
    }
    $pdo->prepare("INSERT INTO rotulo (conceito_id, texto, principal) VALUES (?, ?, ?)")
        ->execute([$conceitoId, $rotulo, $principal ? 1 : 0]);
}

/**
 * Upsert de área por nome (sem hierarquia neste momento — parent_id = NULL).
 * Retorna o id da área.
 */
function kdd_upsert_area(PDO $pdo, string $nome): int
{
    $stmt = $pdo->prepare("SELECT id FROM area WHERE nome = ? LIMIT 1");
    $stmt->execute([$nome]);
    $row = $stmt->fetch();
    if ($row) {
        return (int) $row['id'];
    }
    $pdo->prepare("INSERT INTO area (nome) VALUES (?)")->execute([$nome]);
    return (int) $pdo->lastInsertId();
}

/** POST /fontes/{id}/aprovar */
function fontes_aprovar(int $id): void
{
    $pdo = kdd_db();
    $stmt = $pdo->prepare("SELECT id FROM fonte WHERE id = ?");
    $stmt->execute([$id]);
    if (!$stmt->fetch()) {
        json_error('Fonte não encontrada', 404);
    }
    $pdo->prepare("UPDATE fonte SET status_aprovacao = 'aprovada' WHERE id = ?")
        ->execute([$id]);
    json_out(['ok' => true, 'fonte_id' => $id, 'status_aprovacao' => 'aprovada']);
}

/** POST /fontes/{id}/reprovar */
function fontes_reprovar(int $id): void
{
    $pdo = kdd_db();
    $stmt = $pdo->prepare("SELECT id FROM fonte WHERE id = ?");
    $stmt->execute([$id]);
    if (!$stmt->fetch()) {
        json_error('Fonte não encontrada', 404);
    }
    $pdo->prepare("UPDATE fonte SET status_aprovacao = 'reprovada' WHERE id = ?")
        ->execute([$id]);
    json_out(['ok' => true, 'fonte_id' => $id, 'status_aprovacao' => 'reprovada']);
}
