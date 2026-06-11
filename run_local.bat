@echo off
setlocal

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Criando ambiente virtual local...
    python -m venv .venv
)

call ".venv\Scripts\activate.bat"

echo Instalando dependencias...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

set HOST=127.0.0.1
set PORT=5000
set FLASK_DEBUG=1

echo.
echo Servidor local iniciado em http://127.0.0.1:5000
echo Pressione CTRL+C para parar.
echo.

python app.py
