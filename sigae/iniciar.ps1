# Inicia o SIGAE. Use dentro da pasta sigae:   .\iniciar.ps1
Set-Location $PSScriptRoot

$venv = Join-Path $PSScriptRoot "..\.venv\Scripts\Activate.ps1"
if (Test-Path $venv) { & $venv } else { Write-Host "Ambiente .venv nao encontrado em $venv" -ForegroundColor Yellow }

python manage.py migrate
python manage.py seed

Write-Host ""
Write-Host "Abra no navegador: http://127.0.0.1:8000   (Ctrl+C para parar)" -ForegroundColor Green
python manage.py runserver
