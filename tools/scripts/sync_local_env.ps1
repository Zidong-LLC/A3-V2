$ErrorActionPreference = "Stop"

$projectRoot = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..")
$target = Join-Path $projectRoot ".env"

$candidates = @()
if ($env:A3_ENV_SOURCE) {
    $candidates += $env:A3_ENV_SOURCE
}

$candidates += @(
    "C:\Users\gasto\Desktop\A3 HOY\CONVERSACIONAL-main\.env",
    "C:\Users\gasto\Desktop\A3 ULTIMO\.env",
    "C:\Users\gasto\Desktop\A3\ZIDONG-main\ZIDONG-main\DESARROLLO-A3\1-agente-conversacional\.env",
    "C:\Users\gasto\Desktop\A3\ZIDONG-main\ZIDONG-main\DESARROLLO-A3\DESARROLLO-A3\1-agente-conversacional\.env"
)

$source = $candidates | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) } | Select-Object -First 1

if (-not $source) {
    throw "No encontre un .env fuente. Define A3_ENV_SOURCE con la ruta local del .env."
}

Copy-Item -LiteralPath $source -Destination $target -Force
".env sincronizado en $target"
