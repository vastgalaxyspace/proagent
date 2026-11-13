[CmdletBinding()]
param(
    [string]$AdminUser = "postgres",
    [string]$HostName = "localhost",
    [int]$Port = 5432
)

$ErrorActionPreference = "Stop"

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $repositoryRoot "venv\Scripts\python.exe"

$psqlPath = Get-ChildItem "C:\Program Files\PostgreSQL\*\bin\psql.exe" `
    -ErrorAction SilentlyContinue |
    Sort-Object FullName -Descending |
    Select-Object -First 1 -ExpandProperty FullName

if (-not $psqlPath) {
    throw "psql.exe was not found under C:\Program Files\PostgreSQL."
}

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "The project virtual environment was not found at $pythonPath."
}

$adminPassword = Read-Host `
    "Password for PostgreSQL administrator '$AdminUser'" `
    -AsSecureString

$passwordPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR(
    $adminPassword
)

try {
    $env:PGPASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringBSTR(
        $passwordPointer
    )

    $roleSql = @'
DO $proagent$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_roles WHERE rolname = 'proagent'
    ) THEN
        CREATE ROLE proagent LOGIN;
    END IF;
END
$proagent$;
ALTER ROLE proagent WITH LOGIN PASSWORD 'proagent';
'@

    & $psqlPath `
        --host $HostName `
        --port $Port `
        --username $AdminUser `
        --dbname postgres `
        --set ON_ERROR_STOP=1 `
        --command $roleSql

    if ($LASTEXITCODE -ne 0) {
        throw "Could not create or update the proagent PostgreSQL role."
    }

    $databaseExists = & $psqlPath `
        --host $HostName `
        --port $Port `
        --username $AdminUser `
        --dbname postgres `
        --tuples-only `
        --no-align `
        --set ON_ERROR_STOP=1 `
        --command "SELECT 1 FROM pg_database WHERE datname = 'proagent';"

    if ($LASTEXITCODE -ne 0) {
        throw "Could not check whether the proagent database exists."
    }

    if (-not ($databaseExists -contains "1")) {
        $createdbPath = Join-Path (Split-Path $psqlPath) "createdb.exe"

        & $createdbPath `
            --host $HostName `
            --port $Port `
            --username $AdminUser `
            --owner proagent `
            proagent

        if ($LASTEXITCODE -ne 0) {
            throw "Could not create the proagent database."
        }
    }

    & $psqlPath `
        --host $HostName `
        --port $Port `
        --username $AdminUser `
        --dbname postgres `
        --set ON_ERROR_STOP=1 `
        --command "ALTER DATABASE proagent OWNER TO proagent;"

    if ($LASTEXITCODE -ne 0) {
        throw "Could not set the owner of the proagent database."
    }

    & $psqlPath `
        --host $HostName `
        --port $Port `
        --username $AdminUser `
        --dbname proagent `
        --set ON_ERROR_STOP=1 `
        --command "ALTER SCHEMA public OWNER TO proagent; GRANT ALL ON SCHEMA public TO proagent;"

    if ($LASTEXITCODE -ne 0) {
        throw "Could not grant schema permissions to the proagent role."
    }
}
finally {
    Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($passwordPointer)
}

Push-Location $repositoryRoot
try {
    & $pythonPath -m alembic upgrade head

    if ($LASTEXITCODE -ne 0) {
        throw "Database migrations failed."
    }
}
finally {
    Pop-Location
}

Write-Host "Database setup completed successfully." -ForegroundColor Green
Write-Host "Start the API with: python scripts/run_api.py"
