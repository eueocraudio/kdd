<?php
declare(strict_types=1);

/** Caminho absoluto do arquivo de tokens liberados. */
function kdd_tokens_file(): string
{
    $f = env('TOKENS_FILE', 'tokens.json');
    if ($f === '' || $f[0] !== '/') {
        $f = APP_ROOT . '/' . $f;
    }
    return $f;
}

/**
 * Exige um token válido. Aceita "Authorization: Bearer <token>" ou "X-Token: <token>".
 * Retorna a entrada do token ({token, descricao, perfil}) ou encerra com 401.
 */
function require_token(): array
{
    $hdr = $_SERVER['HTTP_AUTHORIZATION'] ?? ($_SERVER['HTTP_X_TOKEN'] ?? '');
    $token = '';
    if (stripos($hdr, 'Bearer ') === 0) {
        $token = trim(substr($hdr, 7));
    } elseif ($hdr !== '') {
        $token = trim($hdr);
    }

    if ($token === '') {
        json_error('Token ausente', 401);
    }

    $file = kdd_tokens_file();
    if (!is_file($file)) {
        json_error('Lista de tokens não configurada', 500);
    }

    $data = json_decode((string) file_get_contents($file), true);
    foreach (($data['tokens'] ?? []) as $t) {
        if (hash_equals((string) ($t['token'] ?? ''), $token)) {
            return $t;
        }
    }

    json_error('Token inválido', 401);
}
