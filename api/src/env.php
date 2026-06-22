<?php
declare(strict_types=1);

/**
 * Mini-leitor de .env (sem dependências, sem expansão de variáveis).
 * - Ignora linhas vazias e comentários (#).
 * - Remove aspas simples/duplas ao redor do valor; o resto é literal.
 */
function kdd_load_env(string $path): void
{
    static $loaded = [];
    if (isset($loaded[$path])) {
        return;
    }
    if (!is_file($path)) {
        throw new RuntimeException("Arquivo .env não encontrado: $path");
    }

    foreach (file($path, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES) as $line) {
        $line = ltrim($line);
        if ($line === '' || $line[0] === '#') {
            continue;
        }
        $eq = strpos($line, '=');
        if ($eq === false) {
            continue;
        }
        $key = trim(substr($line, 0, $eq));
        $val = trim(substr($line, $eq + 1));

        if (strlen($val) >= 2) {
            $first = $val[0];
            $last  = $val[strlen($val) - 1];
            if (($first === '"' && $last === '"') || ($first === "'" && $last === "'")) {
                $val = substr($val, 1, -1);
            }
        }

        $_ENV[$key] = $val;
    }

    $loaded[$path] = true;
}

function env(string $key, ?string $default = null): ?string
{
    return $_ENV[$key] ?? $default;
}
