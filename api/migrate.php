<?php
declare(strict_types=1);

/**
 * Executor de migrations (CLI). Lê o .env, conecta via PDO e roda os .sql
 * em migrations/ na ordem alfabética. Idempotente (schema usa IF NOT EXISTS /
 * CREATE OR REPLACE). Uso:  php migrate.php
 */

define('APP_ROOT', __DIR__);
require __DIR__ . '/src/env.php';
require __DIR__ . '/src/db.php';

kdd_load_env(__DIR__ . '/.env');
$pdo = kdd_db();

$files = glob(__DIR__ . '/migrations/*.sql');
sort($files);

foreach ($files as $file) {
    $sql = (string) file_get_contents($file);

    // remove linhas de comentário (--) para o split por ';' não quebrar
    $linhas = preg_split('/\r?\n/', $sql) ?: [];
    $limpo = [];
    foreach ($linhas as $l) {
        if (preg_match('/^\s*--/', $l)) {
            continue;
        }
        $limpo[] = $l;
    }
    $sql = implode("\n", $limpo);

    $stmts = array_filter(
        array_map('trim', explode(';', $sql)),
        static fn($s) => $s !== ''
    );

    $n = 0;
    foreach ($stmts as $s) {
        $pdo->exec($s);
        $n++;
    }
    echo basename($file) . ": {$n} statements OK\n";
}

echo "Migrations concluídas.\n";
