param([switch]$Yes)

$ErrorActionPreference = "Stop"
$DbName = "missubibi"
$DbUser = "root"
$SchemaFile = Join-Path $PSScriptRoot "schema.sql"
$SeedFile = Join-Path $PSScriptRoot "seed.sql"

if (-not (Get-Command mysql -ErrorAction SilentlyContinue)) {
    throw "mysql was not found on PATH. Install MySQL and try again."
}
if (-not (Test-Path $SchemaFile) -or -not (Test-Path $SeedFile)) {
    throw "schema.sql or seed.sql was not found in database/."
}
if (-not $Yes) {
    $confirmation = Read-Host "This will DROP and recreate '$DbName'. Type REPLACE to continue"
    if ($confirmation -ne "REPLACE") { Write-Host "Cancelled."; exit 1 }
}

$schemaHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $SchemaFile).Hash.ToLowerInvariant()
$seedHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $SeedFile).Hash.ToLowerInvariant()

Write-Host "==> Dropping and recreating local '$DbName'..."
& mysql -u $DbUser -p -e "DROP DATABASE IF EXISTS $DbName; CREATE DATABASE $DbName;"

Write-Host "==> Loading schema..."
Get-Content -Raw -LiteralPath $SchemaFile | & mysql -u $DbUser -p $DbName

Write-Host "==> Loading data (this can take a minute for 272k+ rows)..."
Get-Content -Raw -LiteralPath $SeedFile | & mysql -u $DbUser -p $DbName

Write-Host "==> Recording the imported repository snapshot..."
$metadataSql = @"
CREATE TABLE IF NOT EXISTS _missubibi_seed_metadata (
  metadata_id TINYINT UNSIGNED NOT NULL PRIMARY KEY,
  schema_sha256 CHAR(64) NOT NULL,
  seed_sha256 CHAR(64) NOT NULL,
  imported_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
REPLACE INTO _missubibi_seed_metadata (metadata_id, schema_sha256, seed_sha256)
VALUES (1, '$schemaHash', '$seedHash');
"@
$metadataSql | & mysql -u $DbUser -p $DbName

Write-Host "Done. Local '$DbName' is now up to date with the repo."
Write-Host "  seed fingerprint: $seedHash"
