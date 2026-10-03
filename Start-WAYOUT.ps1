$ErrorActionPreference = 'Stop'
$projectDir = $PSScriptRoot
$workspaceDir = Split-Path (Split-Path $projectDir -Parent) -Parent
$pythonPath = Join-Path $workspaceDir 'work\.venv\Scripts\python.exe'
$dataDir = Join-Path $workspaceDir 'work\mysql-data'
$mysqlBase = 'C:\Program Files\MySQL\MySQL Server 8.0'
if (!(Test-Path -LiteralPath $pythonPath)) { throw 'Prepared environment not found. Follow README.md to install on this computer.' }
if (!(Get-NetTCPConnection -LocalPort 3307 -State Listen -ErrorAction SilentlyContinue)) {
    if (!(Test-Path -LiteralPath $dataDir)) { throw 'Prepared MySQL data directory is missing. Follow README.md.' }
    $mysqlArgs = @('--no-defaults', ('--basedir="' + $mysqlBase + '"'), ('--datadir="' + $dataDir + '"'), '--port=3307', '--bind-address=127.0.0.1', '--mysqlx=0')
    Start-Process -FilePath (Join-Path $mysqlBase 'bin\mysqld.exe') -ArgumentList $mysqlArgs -WindowStyle Hidden
}
if (!(Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue)) {
    Start-Process -FilePath $pythonPath -ArgumentList @('app.py') -WorkingDirectory $projectDir -WindowStyle Hidden -RedirectStandardOutput (Join-Path $projectDir 'server.log') -RedirectStandardError (Join-Path $projectDir 'server-error.log')
}
Write-Host 'WAYOUT is starting at http://127.0.0.1:5000. Allow MySQL a few seconds to initialise.'
