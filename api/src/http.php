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

/**
 * Falha interna (500): registra o detalhe da exceção no log do servidor mas
 * devolve ao cliente uma mensagem GENÉRICA — não vaza schema/tabela/coluna nem
 * usuário/host do MySQL (mensagens de PDOException com ERRMODE_EXCEPTION).
 */
function json_erro_interno(Throwable $e, string $contexto = 'erro interno'): void
{
    error_log('[kdd] ' . $contexto . ': ' . $e->getMessage() . ' @ ' . $e->getFile() . ':' . $e->getLine());
    json_error('Erro interno ao processar a requisição.', 500);
}

/** Caminho da requisição, sem query string e sem barra final redundante. */
function request_path(): string
{
    $uri  = $_SERVER['REQUEST_URI'] ?? '/';
    $path = parse_url($uri, PHP_URL_PATH) ?: '/';

    // Desconta o diretório do front controller quando a API não está na raiz
    // do domínio (ex.: /kdd/health -> /health). Sem isso, nenhuma rota bate
    // quando a API é servida sob subdiretório (ver rolhama/CORRECAO.md).
    $scriptDir = rtrim(str_replace('\\', '/', dirname((string) ($_SERVER['SCRIPT_NAME'] ?? '/index.php'))), '/');
    if ($scriptDir !== '' && str_starts_with($path, $scriptDir)) {
        $path = substr($path, strlen($scriptDir));
        if ($path === '') {
            $path = '/';
        }
    }

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
