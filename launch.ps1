$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (!(Test-Path -LiteralPath $python)) { throw 'Please run setup.ps1 first.' }
if (!(Test-Path -LiteralPath (Join-Path $PSScriptRoot 'models\welding.pt'))) { throw 'Model is missing. Run setup.ps1 first.' }
$pidFile = Join-Path $PSScriptRoot 'logs\server.pid'
$running = $false
if (Test-Path -LiteralPath $pidFile) {
    $serverId = [int](Get-Content -LiteralPath $pidFile)
    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$serverId" -ErrorAction SilentlyContinue
    $running = $process -and $process.CommandLine -like '*streamlit*' -and $process.CommandLine.Contains($PSScriptRoot)
}
if (!$running) {
    $listener = Get-NetTCPConnection -LocalPort 8501 -State Listen -ErrorAction SilentlyContinue
    if ($listener) { throw 'Port 8501 is occupied by another application.' }
    New-Item -ItemType Directory -Force -Path (Join-Path $PSScriptRoot 'logs') | Out-Null
    $appPath = Join-Path $PSScriptRoot 'app.py'
    $arguments = @('-m', 'streamlit', 'run', ('"' + $appPath + '"'), '--server.address=127.0.0.1', '--server.port=8501', '--server.headless=true')
    $server = Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $PSScriptRoot 'logs\server.log') -RedirectStandardError (Join-Path $PSScriptRoot 'logs\server-error.log')
    $server.Id | Set-Content -LiteralPath $pidFile
}
$healthy = $false
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    try {
        $response = Invoke-WebRequest 'http://127.0.0.1:8501/_stcore/health' -UseBasicParsing -TimeoutSec 2
        if ($response.StatusCode -eq 200) { $healthy = $true; break }
    } catch { Start-Sleep -Milliseconds 500 }
}
if (!$healthy) { throw 'Application startup failed. See logs/server-error.log.' }
Start-Process 'http://127.0.0.1:8501'
Write-Host 'Welding detection is running: http://127.0.0.1:8501'
