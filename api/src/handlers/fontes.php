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
    $pdo    = kdd_db();
    $status = $_GET['status_proc'] ?? null;

    // ⚠️ Sem ?universo= a lista é de TODOS os universos: é assim que o BOT varre a fila
    // (docs/universos.md §6 — o bot não escolhe universo; o push herda o da fonte).
    // Com ?universo= filtra, que é o que o desktop usa.
    $where  = [];
    $params = [];
    if ($status !== null && $status !== '') {
        $where[]  = 'status_proc = ?';
        $params[] = $status;
    }
    if (isset($_GET['universo']) && trim((string) $_GET['universo']) !== '') {
        $where[]  = 'universo_id = ?';
        $params[] = kdd_universo_req($pdo);
    }

    $sql = "SELECT id, titulo, status_proc, status_aprovacao, criado_em, universo_id FROM fonte";
    if ($where) {
        $sql .= ' WHERE ' . implode(' AND ', $where);
    }
    $sql .= ' ORDER BY id DESC';

    $stmt = $pdo->prepare($sql);
    $stmt->execute($params);

    $fontes = array_map(static function (array $f): array {
        $f['id'] = (int) $f['id'];
        $f['universo_id'] = (int) $f['universo_id'];
        return $f;
    }, $stmt->fetchAll());

    json_out(['fontes' => $fontes]);
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

    // Dedup por conteúdo: hash do arquivo, POR UNIVERSO (migration 008). O mesmo PDF pode
    // entrar em dois universos — ler o mesmo documento por duas lentes é caso de uso; o que
    // se barra é reenviar no MESMO universo.
    $hash = hash_file('sha256', $file['tmp_name']);
    $pdo  = kdd_db();
    $uid  = kdd_universo_req($pdo, $_POST['universo'] ?? null);
    // Padrão HERDADO pelo que o bot extrair desta fonte (docs/idioma-pais.md §6).
    $f_idioma = kdd_idioma_valido($_POST['idioma'] ?? '') ?: KDD_IDIOMA_PADRAO;
    $f_pais   = kdd_pais_valido($_POST['pais'] ?? '');
    $dup  = $pdo->prepare(
        "SELECT id, titulo, status_proc, status_aprovacao FROM fonte
          WHERE universo_id = ? AND arquivo_hash = ? LIMIT 1"
    );
    $dup->execute([$uid, $hash]);
    if ($existente = $dup->fetch()) {
        json_out([
            'erro'      => 'PDF já enviado anteriormente neste universo (mesmo conteúdo); não será reprocessado.',
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
        "INSERT INTO fonte (titulo, arquivo_caminho, arquivo_hash, universo_id, idioma, pais,
                            status_proc, status_aprovacao)
         VALUES (?, ?, ?, ?, ?, ?, 'pendente', 'pendente')"
    );
    try {
        $stmt->execute([$titulo, $nome, $hash, $uid, $f_idioma, $f_pais]);
    } catch (PDOException $e) {
        // Corrida: entre o SELECT de dedup acima e este INSERT, outro upload do
        // mesmo conteúdo pode ter inserido primeiro (viola uq_fonte_hash). O UNIQUE
        // garante a integridade; aqui devolvemos 409 limpo e removemos o arquivo
        // órfão que já movemos, em vez de estourar 500 com "Duplicate entry".
        if ($e->getCode() === '23000') {
            @unlink($destino);
            $dup->execute([$uid, $hash]);
            $existente = $dup->fetch() ?: [];
            json_out([
                'erro'      => 'PDF já enviado anteriormente neste universo (mesmo conteúdo); não será reprocessado.',
                'duplicado' => true,
                'fonte'     => [
                    'id'               => (int) ($existente['id'] ?? 0),
                    'titulo'           => $existente['titulo'] ?? null,
                    'status_proc'      => $existente['status_proc'] ?? null,
                    'status_aprovacao' => $existente['status_aprovacao'] ?? null,
                ],
            ], 409);
        }
        @unlink($destino);
        throw $e;
    }
    $id = (int) $pdo->lastInsertId();

    json_out([
        'fonte' => [
            'id'               => $id,
            'titulo'           => $titulo,
            'universo'         => kdd_universo_resumo($pdo, $uid),
            'idioma'           => $f_idioma,
            'pais'             => $f_pais,
            'status_proc'      => 'pendente',
            'status_aprovacao' => 'pendente',
        ],
    ], 201);
}

// POST /fontes/texto — ingestão de TEXTO (não-PDF) com CONTEXTO, vinda de um site externo
// (ex.: o cursohacker manda descrição + transcrição sob o contexto = nome do curso). Grava
// o texto como um .txt no storage (o bot processa igual a um upload .txt) e cria a fonte
// pendente. A ÁREA-RAIZ = contexto é criada/linkada JÁ aqui (o bot adiciona depois as áreas
// achadas no texto; fonte_area é N–N). Idempotente por `ref` (ex.: "aula:<id>"): reenvio do
// mesmo ref ATUALIZA o texto e reprocessa, sem duplicar.
// Body JSON: { "contexto": "...", "texto": "...", "origem": "...", "ref": "..." }.
function fontes_criar_texto(array $auth): void
{
    $body     = json_body();
    $texto    = trim((string) ($body['texto'] ?? ''));
    $contexto = trim((string) ($body['contexto'] ?? ''));
    $origem   = trim((string) ($body['origem'] ?? ''));
    $ref      = trim((string) ($body['ref'] ?? ''));
    if ($texto === '') { json_error('Campo "texto" é obrigatório', 400); }
    if (strlen($texto) > 2000000) { json_error('Texto grande demais (máx. 2 MB)', 413); }

    $pdo = kdd_db();
    $uid = kdd_universo_req($pdo, $body['universo'] ?? null);
    $f_idioma = kdd_idioma_valido($body['idioma'] ?? '') ?: KDD_IDIOMA_PADRAO;
    $f_pais   = kdd_pais_valido($body['pais'] ?? '');
    $dir = kdd_pdf_dir();
    if (!is_dir($dir) && !@mkdir($dir, 0775, true) && !is_dir($dir)) {
        json_error('Não foi possível criar o diretório de storage', 500);
    }
    $titulo = $contexto !== '' ? $contexto : ('Texto ' . ($ref !== '' ? $ref : date('Ymd_His')));

    // Idempotência por ref: se já existe fonte com este ref, ATUALIZA e reprocessa.
    // ...POR UNIVERSO (migration 008): o mesmo 'aula:42' pode existir em cada universo.
    $existente = null;
    if ($ref !== '') {
        $s = $pdo->prepare(
            "SELECT id, arquivo_caminho FROM fonte WHERE universo_id = ? AND ref = ? LIMIT 1"
        );
        $s->execute([$uid, $ref]);
        $existente = $s->fetch() ?: null;
    }

    if ($existente) {
        $fonte_id = (int) $existente['id'];
        @file_put_contents($dir . '/' . (string) $existente['arquivo_caminho'], $texto);
        $pdo->prepare(
            "UPDATE fonte SET titulo = ?, contexto = ?, idioma = ?, pais = ?,
                              status_proc = 'pendente' WHERE id = ?"
        )->execute([$titulo, ($contexto !== '' ? $contexto : null), $f_idioma, $f_pais, $fonte_id]);
    } else {
        $nome = date('Ymd_His') . '_' . bin2hex(random_bytes(6)) . '.txt';
        if (@file_put_contents($dir . '/' . $nome, $texto) === false) {
            json_error('Falha ao salvar o texto', 500);
        }
        $pdo->prepare(
            "INSERT INTO fonte (titulo, arquivo_caminho, arquivo_hash, contexto, ref, universo_id,
                                idioma, pais, status_proc, status_aprovacao)
             VALUES (?, ?, NULL, ?, ?, ?, ?, ?, 'pendente', 'pendente')"
        )->execute([$titulo, $nome, ($contexto !== '' ? $contexto : null),
                    ($ref !== '' ? $ref : null), $uid, $f_idioma, $f_pais]);
        $fonte_id = (int) $pdo->lastInsertId();
    }

    // Área-raiz = contexto (ex.: nome do curso): cria/garante e linka à fonte.
    if ($contexto !== '') {
        $area_id = kdd_upsert_area($pdo, $contexto, $uid);
        $pdo->prepare("INSERT IGNORE INTO fonte_area (fonte_id, area_id) VALUES (?, ?)")
            ->execute([$fonte_id, $area_id]);
    }

    json_out([
        'fonte' => [
            'id'          => $fonte_id,
            'titulo'      => $titulo,
            'contexto'    => $contexto,
            'ref'         => $ref,
            'origem'      => $origem,
            'universo'    => kdd_universo_resumo($pdo, $uid),
            'idioma'      => $f_idioma,
            'pais'        => $f_pais,
            'status_proc' => 'pendente',
        ],
    ], $existente ? 200 : 202);
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
    $stmt = $pdo->prepare("SELECT id, universo_id FROM fonte WHERE id = ?");
    $stmt->execute([$id]);
    $f = $stmt->fetch();
    if (!$f) {
        json_error('Fonte não encontrada', 404);
    }
    $uid = (int) $f['universo_id'];   // as áreas inferidas entram no universo DA FONTE

    // Valida status_proc antes de abrir transação
    $status_validos = ['processando', 'processado', 'erro'];
    if (isset($body['status_proc']) && !in_array($body['status_proc'], $status_validos, true)) {
        json_error('status_proc inválido. Valores aceitos: ' . implode(', ', $status_validos), 400);
    }

    // Status + áreas num único bloco atômico: ou tudo, ou nada (evita estado
    // parcial — status novo com só parte das áreas vinculadas).
    $pdo->beginTransaction();
    try {
        if (isset($body['status_proc'])) {
            $pdo->prepare("UPDATE fonte SET status_proc = ? WHERE id = ?")
                ->execute([$body['status_proc'], $id]);
        }

        if (isset($body['areas']) && is_array($body['areas'])) {
            foreach ($body['areas'] as $nome_area) {
                $nome_area = trim((string) $nome_area);
                if ($nome_area === '') {
                    continue;
                }
                $area_id = kdd_upsert_area($pdo, $nome_area, $uid);
                $pdo->prepare(
                    "INSERT IGNORE INTO fonte_area (fonte_id, area_id) VALUES (?, ?)"
                )->execute([$id, $area_id]);
            }
        }
        $pdo->commit();
    } catch (Throwable $e) {
        $pdo->rollBack();
        json_erro_interno($e, 'atualizar fonte ' . $id);
    }

    // Devolve fonte atualizada
    $stmt = $pdo->prepare(
        "SELECT id, titulo, status_proc, status_aprovacao, universo_id FROM fonte WHERE id = ?"
    );
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
    $stmt = $pdo->prepare(
        "SELECT id, status_proc, universo_id, idioma, pais FROM fonte WHERE id = ?"
    );
    $stmt->execute([$id]);
    $fonte = $stmt->fetch();
    if (!$fonte) {
        json_error('Fonte não encontrada', 404);
    }
    // ⚠️ O universo vem DA FONTE, nunca do corpo (docs/universos.md §6): quem ingeriu
    // escolheu o universo; o bot só processa o que está na fila e não decide isso.
    $uid = (int) $fonte['universo_id'];
    // Idioma e país da FONTE são o PADRÃO do que sai dela (docs/idioma-pais.md §6): um PDF
    // da legislação brasileira ingerido com pais=BR faz os conceitos nascerem BR, sem a IA
    // precisar acertar item por item. A IA pode sobrepor por conceito/proposição.
    $f_idioma = kdd_idioma_valido($fonte['idioma'] ?? '') ?: KDD_IDIOMA_PADRAO;
    $f_pais   = kdd_pais_valido($fonte['pais'] ?? '');

    $conceitos_raw   = $body['conceitos']   ?? [];
    $proposicoes_raw = $body['proposicoes'] ?? [];

    if (!is_array($conceitos_raw) || !is_array($proposicoes_raw)) {
        json_error('Corpo inválido: esperado { conceitos: [...], proposicoes: [...] }', 400);
    }

    $pdo->beginTransaction();
    try {
        // ── 0. REPLACE (não acumular): remove os vínculos DESTA fonte antes de reinserir.
        // Reprocessar uma fonte SUBSTITUI o mapa dela em vez de empilhar (senão conceitos de
        // uma extração antiga/errada ficariam pra sempre — ex.: aula de APT com conceitos de
        // Redes). Só os links POR-FONTE: conceitos, proposições e áreas globais permanecem
        // (são deduplicados e compartilhados por várias fontes). fonte_area NÃO é limpo aqui
        // (preserva a área-raiz = contexto criada na ingestão). ──
        $pdo->prepare("DELETE FROM conceito_fonte WHERE fonte_id = ?")->execute([$id]);
        $pdo->prepare("DELETE FROM referencia    WHERE fonte_id = ?")->execute([$id]);

        // ── 1. Upsert de conceitos; monta mapa rotulo→conceito_id ──
        $mapa_rotulo   = [];   // rotulo (minusc.) → conceito_id (namespace do push)
        $ids_conceitos = [];   // set de conceito_id distintos tocados (p/ contagem)

        foreach ($conceitos_raw as $c) {
            $rotulo  = trim((string) ($c['rotulo']  ?? ''));
            $sentido = trim((string) ($c['sentido'] ?? $rotulo));
            $areas   = is_array($c['areas'] ?? null) ? $c['areas'] : [];
            $tipo    = kdd_tipo_valido($c['tipo'] ?? null);
            // idioma do RÓTULO e país do CONCEITO; ausentes ⇒ o padrão da fonte
            $c_idioma = kdd_idioma_valido($c['idioma'] ?? '') ?: $f_idioma;
            $c_pais   = array_key_exists('pais', $c) ? kdd_pais_valido($c['pais']) : $f_pais;

            if ($rotulo === '') {
                continue;
            }

            // Identidade no nível do SENTIDO (Novak/spec): reaproveita o conceito de
            // mesmo sentido; senão cria. NÃO funde homônimos — mesmo rótulo com
            // sentidos distintos = conceitos distintos. A área é dimensão N–N de
            // classificação, não critério de identidade.
            $conceito_id = kdd_resolver_conceito($pdo, $rotulo, $sentido, $uid, $c_pais, $c_idioma);

            // Tipo (entidade/classe/processo/atributo) entra no cálculo do VALOR da proposição
            // (docs/valor-conhecimento.md §3). O bot só PREENCHE o que está NULL — curadoria
            // humana (editor) tem a palavra final e não é sobrescrita por uma re-extração.
            if ($tipo !== null) {
                $pdo->prepare("UPDATE conceito SET tipo = ? WHERE id = ? AND tipo IS NULL")
                    ->execute([$tipo, $conceito_id]);
            }

            // Vincula conceito às áreas e à fonte
            foreach ($areas as $nome_area) {
                $nome_area = trim((string) $nome_area);
                if ($nome_area === '') {
                    continue;
                }
                $area_id = kdd_upsert_area($pdo, $nome_area, $uid);
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
            // País da PROPOSIÇÃO: a mesma tripla pode valer num país e não noutro.
            $p_pais         = array_key_exists('pais', $p) ? kdd_pais_valido($p['pais']) : $f_pais;
            // Forma inglesa da relação (substrato da análise) e o sentimento MEDIDO PELO BOT
            // com vaderSentiment/TextBlob. A API não pontua, só guarda (docs/sentimento.md).
            $p_rel_en       = trim((string) ($p['relacao_en'] ?? ''));
            $p_polaridade   = kdd_polaridade_valida($p['polaridade'] ?? null);
            $p_subjetiv     = kdd_subjetividade_valida($p['subjetividade'] ?? null);

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
                $dest_id = kdd_resolver_conceito($pdo, $dest_rotulo_orig, $dest_sentido, $uid,
                                                 $f_pais, $f_idioma);
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
                  WHERE conceito_origem = ? AND relacao = ? AND conceito_destino = ?
                    AND pais = ? LIMIT 1"
            );
            $s->execute([$orig_id, $relacao, $dest_id, $p_pais]);
            $prop = $s->fetch();

            if ($prop) {
                $prop_id = (int) $prop['id'];
            } else {
                $pdo->prepare(
                    "INSERT INTO proposicao (conceito_origem, relacao, conceito_destino, pais,
                                             relacao_en)
                     VALUES (?, ?, ?, ?, ?)"
                )->execute([$orig_id, $relacao, $dest_id, $p_pais,
                            $p_rel_en !== '' ? $p_rel_en : null]);
                $prop_id = (int) $pdo->lastInsertId();
                $props_criadas++;
            }

            // Preenche relacao_en se a proposição já existia sem ela (dado antigo).
            if ($p_rel_en !== '') {
                $pdo->prepare("UPDATE proposicao SET relacao_en = ? WHERE id = ? AND relacao_en IS NULL")
                    ->execute([$p_rel_en, $prop_id]);
            }

            // Referência: esta fonte sustenta esta proposição, COM o enquadramento dela.
            // O sentimento é por (proposição, fonte) — duas fontes podem afirmar a mesma
            // tripla com cargas diferentes, e reprovar uma remove só a contribuição dela.
            $pdo->prepare(
                "INSERT INTO referencia (proposicao_id, fonte_id, polaridade, subjetividade)
                 VALUES (?, ?, ?, ?)
                 ON DUPLICATE KEY UPDATE polaridade = VALUES(polaridade),
                                         subjetividade = VALUES(subjetividade)"
            )->execute([$prop_id, $id, $p_polaridade, $p_subjetiv]);
        }

        // Marca fonte como processada
        $pdo->prepare("UPDATE fonte SET status_proc = 'processado' WHERE id = ?")
            ->execute([$id]);

        // APROVAÇÃO AUTOMÁTICA (decisão IV do idealizador — docs/valor-conhecimento.md §4):
        // "é impossível aprovar tanta informação; vamos assumir que entrou, tá aprovado".
        // O que ENTROU conta na certeza na hora; o humano age por VETO (/reprovar), não por
        // liberação. 'reprovada' é respeitada (só promove quem está 'pendente'). Desligável
        // com APROVACAO_AUTOMATICA=0 no .env da API.
        $auto = env('APROVACAO_AUTOMATICA', '1') !== '0';
        if ($auto) {
            $pdo->prepare(
                "UPDATE fonte SET status_aprovacao = 'aprovada'
                  WHERE id = ? AND status_aprovacao = 'pendente'"
            )->execute([$id]);
        }
        $s_ap = $pdo->prepare("SELECT status_aprovacao FROM fonte WHERE id = ?");
        $s_ap->execute([$id]);
        $status_aprovacao = (string) $s_ap->fetchColumn();

        $pdo->commit();

        json_out([
            'ok'               => true,
            'conceitos'        => count($ids_conceitos),
            'proposicoes'      => $props_criadas,
            'fonte_id'         => $id,
            'universo'         => kdd_universo_resumo($pdo, $uid),
            'status_proc'      => 'processado',
            'status_aprovacao' => $status_aprovacao,
        ]);
    } catch (Throwable $e) {
        $pdo->rollBack();
        // O push falhou e o rollback desfez tudo, mas o bot já pusera a fonte em
        // 'processando'. Marca 'erro' (fora da transação abortada) para não ficar
        // presa e continuar reprocessável (/reprocessar só aceita 'erro'). Não
        // rebaixa uma fonte já 'processado' (re-push idempotente que falhou).
        try {
            $pdo->prepare("UPDATE fonte SET status_proc = 'erro' WHERE id = ? AND status_proc <> 'processado'")
                ->execute([$id]);
        } catch (Throwable $e2) {
            error_log('[kdd] falha ao marcar fonte ' . $id . ' como erro: ' . $e2->getMessage());
        }
        json_erro_interno($e, 'push de mapa da fonte ' . $id);
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
function kdd_resolver_conceito(PDO $pdo, string $rotulo, string $sentido, int $universoId = 1,
                               string $pais = '', string $idioma = KDD_IDIOMA_PADRAO): int
{
    $sentido = trim($sentido) !== '' ? trim($sentido) : trim($rotulo);
    $pais    = kdd_pais_valido($pais);   // '' = universal

    // Identidade = (universo, pais, sentido) — docs/universos.md §2 + docs/idioma-pais.md §4.
    // O MESMO sentido em outro universo, ou no mesmo universo com outro PAÍS, é OUTRO
    // conceito: "Imposto de Renda" (BR) e o equivalente português não são tradução, são
    // institutos distintos. O IDIOMA, ao contrário, NÃO entra aqui — é só superfície.
    $s = $pdo->prepare(
        "SELECT id FROM conceito WHERE universo_id = ? AND pais = ? AND sentido = ? LIMIT 1"
    );
    $s->execute([$universoId, $pais, $sentido]);
    $row = $s->fetch();

    if ($row) {
        $conceito_id = (int) $row['id'];
        kdd_garantir_rotulo($pdo, $conceito_id, $rotulo, false, $idioma);
        return $conceito_id;
    }

    try {
        $pdo->prepare("INSERT INTO conceito (sentido, universo_id, pais) VALUES (?, ?, ?)")
            ->execute([$sentido, $universoId, $pais]);
        $conceito_id = (int) $pdo->lastInsertId();
    } catch (PDOException $e) {
        // Corrida: outro processo (ex.: curador) criou o MESMO sentido entre o
        // SELECT e este INSERT. Protegido por UNIQUE(sentido) (migration 004) —
        // aqui reaproveitamos o conceito existente em vez de fragmentar a
        // identidade em dois ids. Leitura com FOR UPDATE para enxergar a linha
        // recém-commitada mesmo sob REPEATABLE READ. (UNIQUE agora é (universo_id, sentido),
        // migration 008.)
        if ($e->getCode() !== '23000') {
            throw $e;
        }
        $lock = $pdo->prepare(
            "SELECT id FROM conceito WHERE universo_id = ? AND pais = ? AND sentido = ?
              LIMIT 1 FOR UPDATE"
        );
        $lock->execute([$universoId, $pais, $sentido]);
        $conceito_id = (int) $lock->fetchColumn();
        if ($conceito_id <= 0) {
            throw $e;
        }
        kdd_garantir_rotulo($pdo, $conceito_id, $rotulo, false, $idioma);
        return $conceito_id;
    }
    kdd_garantir_rotulo($pdo, $conceito_id, $rotulo, true, $idioma);
    return $conceito_id;
}

/**
 * Garante que o conceito tenha o rótulo dado (sem duplicar). Marca como principal
 * apenas quando solicitado (tipicamente no rótulo de criação do conceito).
 */
function kdd_garantir_rotulo(PDO $pdo, int $conceitoId, string $rotulo, bool $principal,
                             string $idioma = KDD_IDIOMA_PADRAO): void
{
    $rotulo = trim($rotulo);
    if ($rotulo === '') {
        return;
    }
    // O IDIOMA entra na unicidade (migration 009): o mesmo texto pode repetir em idiomas
    // diferentes ("Internet" em pt-BR e en é o mesmo texto, dois rótulos do conceito).
    $idioma = kdd_idioma_valido($idioma) ?: KDD_IDIOMA_PADRAO;
    $s = $pdo->prepare(
        "SELECT id FROM rotulo WHERE conceito_id = ? AND idioma = ? AND texto = ? LIMIT 1"
    );
    $s->execute([$conceitoId, $idioma, $rotulo]);
    if ($s->fetch()) {
        return;
    }
    $pdo->prepare("INSERT INTO rotulo (conceito_id, texto, idioma, principal) VALUES (?, ?, ?, ?)")
        ->execute([$conceitoId, $rotulo, $idioma, $principal ? 1 : 0]);
}

/**
 * Upsert de área por nome DENTRO DE UM UNIVERSO (sem hierarquia aqui — parent_id = NULL).
 * Retorna o id da área.
 *
 * Nota: `area(universo_id, nome)` é índice comum, não único (ver migration 008 §4), então o
 * dedup continua sendo este SELECT-antes-de-INSERT.
 */
function kdd_upsert_area(PDO $pdo, string $nome, int $universoId = 1): int
{
    $stmt = $pdo->prepare("SELECT id FROM area WHERE universo_id = ? AND nome = ? LIMIT 1");
    $stmt->execute([$universoId, $nome]);
    $row = $stmt->fetch();
    if ($row) {
        return (int) $row['id'];
    }
    $pdo->prepare("INSERT INTO area (nome, universo_id) VALUES (?, ?)")->execute([$nome, $universoId]);
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

/**
 * POST /fontes/{id}/reprocessar
 * Recoloca a fonte na fila (status_proc=pendente) APENAS se ela falhou (erro).
 * Fontes processadas com sucesso não podem ser reprocessadas.
 */
function fontes_reprocessar(int $id): void
{
    $pdo = kdd_db();
    $stmt = $pdo->prepare("SELECT status_proc FROM fonte WHERE id = ?");
    $stmt->execute([$id]);
    $f = $stmt->fetch();
    if (!$f) {
        json_error('Fonte não encontrada', 404);
    }
    if ($f['status_proc'] !== 'erro') {
        json_error('Só é possível reprocessar uma fonte com status de erro.', 409);
    }
    $pdo->prepare("UPDATE fonte SET status_proc = 'pendente' WHERE id = ?")->execute([$id]);
    json_out(['ok' => true, 'fonte_id' => $id, 'status_proc' => 'pendente']);
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
