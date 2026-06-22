<?php
declare(strict_types=1);

/** Responde JSON e encerra. */
function json_out($data, int $status = 200): void
{
    http_response_code($status);
    header('Content-Type: application/json; charset=utf-8');
    echo json_encode($data, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
    exit;
}

/** Responde um erro JSON e encerra. */
function json_error(string $msg, int $status = 400): void
{
    json_out(['erro' => $msg], $status);
}

/** Caminho da requisição, sem query string e sem barra final redundante. */
function request_path(): string
{
    $uri  = $_SERVER['REQUEST_URI'] ?? '/';
    $path = parse_url($uri, PHP_URL_PATH) ?: '/';
    if ($path !== '/') {
        $path = rtrim($path, '/');
    }
    return $path;
}

/** Corpo JSON da requisição como array (vazio se não houver). */
function json_body(): array
{
    $raw = file_get_contents('php://input');
    if ($raw === '' || $raw === false) {
        return [];
    }
    $data = json_decode($raw, true);
    return is_array($data) ? $data : [];
}
