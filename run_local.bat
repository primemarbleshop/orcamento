@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

set "LOCAL_VENV=%CD%\.venv"
set "VENV_PYTHON=%LOCAL_VENV%\Scripts\python.exe"

echo Verificando ambiente local...

if exist ".venv\pyvenv.cfg" (
    findstr /I /C:"%CD%" ".venv\pyvenv.cfg" >nul 2>nul
    if errorlevel 1 (
        echo Ambiente virtual antigo/copiado de outro computador detectado.
        echo Recriando .venv local...
        rmdir /S /Q ".venv"
    )
)

:CRIAR_OU_VALIDAR_VENV
if not exist "%VENV_PYTHON%" (
    echo Criando ambiente virtual local...
    py -3 -m venv .venv 2>nul
    if errorlevel 1 (
        python -m venv .venv
    )
    if errorlevel 1 (
        echo.
        echo ERRO: nao foi possivel criar o ambiente virtual.
        echo Instale o Python e marque a opcao "Add Python to PATH".
        pause
        exit /b 1
    )
)

call ".venv\Scripts\activate.bat"
if errorlevel 1 (
    echo.
    echo ERRO: nao foi possivel ativar o ambiente virtual.
    pause
    exit /b 1
)

python -c "import os,sys; esperado=os.path.abspath(os.environ['LOCAL_VENV']).lower(); atual=os.path.abspath(sys.prefix).lower(); raise SystemExit(0 if atual==esperado else 1)" >nul 2>nul
if errorlevel 1 (
    echo Ambiente virtual invalido. Recriando...
    call deactivate >nul 2>nul
    rmdir /S /Q ".venv"
    goto CRIAR_OU_VALIDAR_VENV
)

echo Python em uso:
python -c "import sys; print(sys.executable)"

echo.
echo Instalando/verificando dependencias...
python -m pip install --upgrade pip
if errorlevel 1 (
    echo.
    echo ERRO ao atualizar o pip.
    pause
    exit /b 1
)

python -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo ERRO ao instalar dependencias.
    pause
    exit /b 1
)

set HOST=127.0.0.1
set PORT=5000
set FLASK_DEBUG=0
set OPEN_BROWSER=1

echo.
echo Iniciando servidor local em http://127.0.0.1:5000
echo Aguarde o navegador abrir. Para parar, pressione CTRL+C.
echo.

python app.py
set "APP_EXIT=%ERRORLEVEL%"

echo.
if not "%APP_EXIT%"=="0" (
    echo O servidor encerrou com erro. Leia a mensagem acima.
) else (
    echo O servidor foi encerrado.
)
pause
exit /b %APP_EXIT%
