param([ValidateRange(1024, 65535)][int]$Port = 8501)
$ErrorActionPreference = 'Stop'
$logName = if ($Port -eq 8501) { 'server' } else { "server-$Port" }
$pidFile = Join-Path $PSScriptRoot "logs\$logName.pid"
$appPattern = '(?i)(?:^|["\s])' + [regex]::Escape((Join-Path $PSScriptRoot 'app.py')) + '(?:["\s]|$)'
if (Test-Path -LiteralPath $pidFile) {
    $serverId = 0
    if ([int]::TryParse((Get-Content -LiteralPath $pidFile -Raw).Trim(), [ref]$serverId) -and $serverId -gt 0) {
        $process = Get-CimInstance Win32_Process -Filter "ProcessId=$serverId" -ErrorAction SilentlyContinue
        if ($process -and $process.CommandLine -like '*streamlit*' -and $process.CommandLine -match $appPattern -and $process.CommandLine -match "(?:--server.port[=\s]+)$Port(?:\s|$)") {
            & taskkill.exe /PID $serverId /T /F
            if ($LASTEXITCODE -ne 0) { throw "Could not stop server process $serverId." }
        }
    }
    Remove-Item -LiteralPath $pidFile
}
Write-Host 'Welding detection stopped.'
