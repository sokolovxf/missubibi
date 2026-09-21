param([switch]$Sync)

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

$expectedSchema = (Get-FileHash -Algorithm SHA256 -LiteralPath $SchemaFile).Hash.ToLowerInvariant()
$expectedSeed = (Get-FileHash -Algorithm SHA256 -LiteralPath $SeedFile).Hash.ToLowerInvariant()
$metadata = (& mysql -u $DbUser -p -N -B $DbName -e "SELECT schema_sha256, seed_sha256 FROM _missubibi_seed_metadata WHERE metadata_id = 1" | Out-String).Trim()
$parts = $metadata -split "\s+"
$currentSchema = if ($parts.Count -gt 0) { $parts[0] } else { "" }
$currentSeed = if ($parts.Count -gt 1) { $parts[1] } else { "" }

if ($currentSchema -eq $expectedSchema -and $currentSeed -eq $expectedSeed) {
    Write-Host "Local '$DbName' is current with this checkout."
    Write-Host "  seed fingerprint: $currentSeed"
    exit 0
}

Write-Host "Local '$DbName' is missing or out of date with this checkout."
Write-Host "  checkout seed: $expectedSeed"
if ($Sync) {
    & (Join-Path $PSScriptRoot "import_db.ps1") -Yes
    exit $LASTEXITCODE
}

Write-Host "Run '.\database\ensure_current.ps1 -Sync' to refresh the local database."
exit 2
