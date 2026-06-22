<?php
declare(strict_types=1);

/**
 * Front controller da KDD Web API (armazém).
 * Layout Hostinger: este arquivo e tudo o mais ficam DENTRO de public_html;
 * o acesso direto a .env / tokens.json / src / storage é bloqueado no .htaccess.
 */

define('APP_ROOT', __DIR__);

require APP_ROOT . '/src/env.php';
require APP_ROOT . '/src/http.php';
require APP_ROOT . '/src/db.php';
require APP_ROOT . '/src/auth.php';
require APP_ROOT . '/src/handlers/fontes.php';
require APP_ROOT . '/src/handlers/consulta.php';
require APP_ROOT . '/src/handlers/editor.php';

kdd_load_env(APP_ROOT . '/.env');

set_exception_handler(function (Throwable $e): void {
    json_error('Erro interno: ' . $e->getMessage(), 500);
});

$method = $_SERVER['REQUEST_METHOD'] ?? 'GET';
$path   = request_path();

// --- Rota pública (sem token): saúde ---
if ($method === 'GET' && $path === '/health') {
    json_out(['ok' => true, 'servico' => 'kdd-api']);
}

// --- Daqui em diante, exige token ---
$auth = require_token();

if ($method === 'GET' && $path === '/ping') {
    json_out(['pong' => true, 'perfil' => $auth['perfil'] ?? null]);
}

if ($path === '/fontes') {
    if ($method === 'GET')  { fontes_listar(); }
    if ($method === 'POST') { fontes_criar($auth); }
}

if (preg_match('#^/fontes/(\d+)$#', $path, $m)) {
    if ($method === 'GET')   { fontes_obter((int) $m[1]); }
    if ($method === 'PATCH') { fontes_atualizar((int) $m[1]); }
}

if (preg_match('#^/fontes/(\d+)/arquivo$#', $path, $m) && $method === 'GET') {
    fontes_baixar((int) $m[1]);
}

if (preg_match('#^/fontes/(\d+)/mapa$#', $path, $m) && $method === 'GET') {
    fonte_mapa((int) $m[1]);
}

if (preg_match('#^/fontes/(\d+)/mapas$#', $path, $m) && $method === 'POST') {
    fontes_mapas((int) $m[1]);
}

if (preg_match('#^/fontes/(\d+)/aprovar$#', $path, $m) && $method === 'POST') {
    fontes_aprovar((int) $m[1]);
}

if (preg_match('#^/fontes/(\d+)/reprovar$#', $path, $m) && $method === 'POST') {
    fontes_reprovar((int) $m[1]);
}

if (preg_match('#^/fontes/(\d+)/reprocessar$#', $path, $m) && $method === 'POST') {
    fontes_reprocessar((int) $m[1]);
}

// --- Consulta (somente leitura; humanos e máquinas) ---
if ($method === 'GET' && $path === '/areas') {
    areas_arvore();
}

if ($method === 'GET' && $path === '/conceitos') {
    conceitos_listar();
}

if (preg_match('#^/conceitos/(\d+)$#', $path, $m) && $method === 'GET') {
    conceitos_obter((int) $m[1]);
}

if ($method === 'GET' && $path === '/proposicoes') {
    proposicoes_listar();
}

if ($method === 'GET' && $path === '/constelacao') {
    constelacao();
}

// --- Editor manual de mapas (escrita; exige perfil validador) ---
if ($path === '/proposicoes' && $method === 'POST') {
    proposicao_criar($auth);
}
if (preg_match('#^/proposicoes/(\d+)$#', $path, $m)) {
    if ($method === 'PATCH')  { proposicao_editar($auth, (int) $m[1]); }
    if ($method === 'DELETE') { proposicao_remover($auth, (int) $m[1]); }
}

if ($path === '/conceitos' && $method === 'POST') {
    conceito_criar($auth);
}
if (preg_match('#^/conceitos/(\d+)$#', $path, $m) && $method === 'PATCH') {
    conceito_editar($auth, (int) $m[1]);
}
if (preg_match('#^/conceitos/(\d+)/rotulos$#', $path, $m) && $method === 'POST') {
    conceito_add_rotulo($auth, (int) $m[1]);
}
if (preg_match('#^/conceitos/(\d+)/areas$#', $path, $m) && $method === 'POST') {
    conceito_add_area($auth, (int) $m[1]);
}
if (preg_match('#^/conceitos/(\d+)/areas/(\d+)$#', $path, $m) && $method === 'DELETE') {
    conceito_rem_area($auth, (int) $m[1], (int) $m[2]);
}
if (preg_match('#^/conceitos/(\d+)/merge$#', $path, $m) && $method === 'POST') {
    conceito_merge($auth, (int) $m[1]);
}
if (preg_match('#^/conceitos/(\d+)/split$#', $path, $m) && $method === 'POST') {
    conceito_split($auth, (int) $m[1]);
}

if (preg_match('#^/rotulos/(\d+)$#', $path, $m)) {
    if ($method === 'PATCH')  { rotulo_editar($auth, (int) $m[1]); }
    if ($method === 'DELETE') { rotulo_remover($auth, (int) $m[1]); }
}

if ($path === '/areas' && $method === 'POST') {
    area_criar($auth);
}
if (preg_match('#^/areas/(\d+)$#', $path, $m)) {
    if ($method === 'PATCH')  { area_editar($auth, (int) $m[1]); }
    if ($method === 'DELETE') { area_remover($auth, (int) $m[1]); }
}

json_error("Rota não encontrada: {$method} {$path}", 404);
