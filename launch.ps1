param(
    [ValidateRange(1024, 65535)][int]$Port = 8501,
    [switch]$NoBrowser
)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (!(Test-Path -LiteralPath $python)) { throw 'Please run setup.ps1 first.' }
if (!(Test-Path -LiteralPath (Join-Path $PSScriptRoot 'models\welding.pt')) -and
    !(Test-Path -LiteralPath (Join-Path $PSScriptRoot 'models\welding.onnx'))) { throw 'Model is missing. Run setup.ps1 first.' }
$logName = if ($Port -eq 8501) { 'server' } else { "server-$Port" }
$pidFile = Join-Path $PSScriptRoot "logs\$logName.pid"
$appPath = Join-Path $PSScriptRoot 'app.py'
$appPattern = '(?i)(?:^|["\s])' + [regex]::Escape($appPath) + '(?:["\s]|$)'
$url = "http://127.0.0.1:$Port"
$running = $false
if (Test-Path -LiteralPath $pidFile) {
    $serverId = 0
    if ([int]::TryParse((Get-Content -LiteralPath $pidFile -Raw).Trim(), [ref]$serverId) -and $serverId -gt 0) {
        $process = Get-CimInstance Win32_Process -Filter "ProcessId=$serverId" -ErrorAction SilentlyContinue
        $running = $process -and $process.CommandLine -like '*streamlit*' -and $process.CommandLine -match $appPattern -and $process.CommandLine -match "(?:--server.port[=\s]+)$Port(?:\s|$)"
    }
}
if (!$running) {
    $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($listener) {
        $process = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)" -ErrorAction SilentlyContinue
        if ($process -and $process.CommandLine -like '*streamlit*' -and $process.CommandLine -match $appPattern) {
            $running = $true
            New-Item -ItemType Directory -Force -Path (Join-Path $PSScriptRoot 'logs') | Out-Null
            $process.ProcessId | Set-Content -LiteralPath $pidFile
        } else {
            throw "Port $Port is occupied by another application."
        }
    }
}
if (!$running) {
    New-Item -ItemType Directory -Force -Path (Join-Path $PSScriptRoot 'logs') | Out-Null
    $arguments = @('-m', 'streamlit', 'run', ('"' + $appPath + '"'), '--server.address=127.0.0.1', "--server.port=$Port", '--server.headless=true')
    $server = Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $PSScriptRoot "logs\$logName.log") -RedirectStandardError (Join-Path $PSScriptRoot "logs\$logName-error.log")
    $server.Id | Set-Content -LiteralPath $pidFile
}
$healthy = $false
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    try {
        $response = Invoke-WebRequest "$url/_stcore/health" -UseBasicParsing -TimeoutSec 2
        if ($response.StatusCode -eq 200) { $healthy = $true; break }
    } catch { Start-Sleep -Milliseconds 500 }
}
if (!$healthy) { throw "Application startup failed. See logs/$logName-error.log." }
if (!$NoBrowser) { Start-Process $url }
Write-Host "Welding detection is running: $url"
