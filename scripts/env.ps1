# Load variables from .env into the current PowerShell session (run with a leading dot: . .\scripts\env.ps1)
$envFile = Join-Path (Get-Location) ".env"
if (-not (Test-Path $envFile)) {
    Write-Host "No .env found in $(Get-Location). Run this from the project root."
    return
}
Get-Content $envFile | ForEach-Object {
    if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$') {
        [Environment]::SetEnvironmentVariable($matches[1], $matches[2], 'Process')
    }
}
$env:DBT_PROFILES_DIR = (Join-Path (Get-Location) "dbt_project")
Write-Host "Loaded .env and set DBT_PROFILES_DIR=$env:DBT_PROFILES_DIR"