$ErrorActionPreference = 'Stop'
$pidFile = Join-Path $PSScriptRoot 'logs\server.pid'
if (Test-Path -LiteralPath $pidFile) {
    $serverId = [int](Get-Content -LiteralPath $pidFile)
    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$serverId" -ErrorAction SilentlyContinue
    if ($process -and $process.CommandLine -like '*streamlit*' -and $process.CommandLine.Contains($PSScriptRoot)) {
        & taskkill.exe /PID $serverId /T /F
    }
    Remove-Item -LiteralPath $pidFile
}
Write-Host 'Welding detection stopped.'
