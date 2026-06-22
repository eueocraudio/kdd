<?php
declare(strict_types=1);

/** Conexão PDO singleton com o MySQL, configurada via .env. */
function kdd_db(): PDO
{
    static $pdo = null;
    if ($pdo instanceof PDO) {
        return $pdo;
    }

    $host    = env('DB_HOST', 'localhost');
    $port    = env('DB_PORT', '3306');
    $name    = env('DB_NAME', '');
    $user    = env('DB_USER', '');
    $pass    = env('DB_PASS', '');
    $charset = env('DB_CHARSET', 'utf8mb4');

    $dsn = "mysql:host={$host};port={$port};dbname={$name};charset={$charset}";

    $pdo = new PDO($dsn, $user, $pass, [
        PDO::ATTR_ERRMODE            => PDO::ERRMODE_EXCEPTION,
        PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
        PDO::ATTR_EMULATE_PREPARES   => false,
    ]);

    return $pdo;
}
