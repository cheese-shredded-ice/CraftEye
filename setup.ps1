$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
New-Item -ItemType Directory -Force -Path logs | Out-Null
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (!(Test-Path -LiteralPath $python)) {
    # Reuse an existing CPU PyTorch only when this exact local runtime is available.
    if (Test-Path -LiteralPath 'D:\Python\python.exe') {
        & 'D:\Python\python.exe' -m venv --system-site-packages .venv
    } else {
        & py -3.13 -m venv .venv
    }
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.13 environment creation failed.' }
}
& $python -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
& $python scripts\download_model.py
if ($LASTEXITCODE -ne 0) { throw 'Model download failed.' }
& $python scripts\download_dataset.py
if ($LASTEXITCODE -ne 0) { throw 'Dataset download failed. Run setup again to resume.' }
& $python scripts\verify_install.py
if ($LASTEXITCODE -ne 0) { throw 'Verification failed.' }
Write-Host 'Setup complete. Run launch.ps1 to open the application.'
