@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"

set "PYTHONHOME="
set "PYTHONPATH="
set "HOST=127.0.0.1"
set "PORT=5000"
set "FLASK_DEBUG=0"
set "OPEN_BROWSER=1"

set "LOCAL_VENV=%CD%\.venv"
set "VENV_PYTHON=%LOCAL_VENV%\Scripts\python.exe"

cls
echo Verificando ambiente local...
echo Pasta do projeto: %CD%
echo.

if not exist "app.py" goto ERRO_PASTA
if not exist "requirements.txt" goto ERRO_REQ

rem Nao usa py.exe nem python do PATH, porque neste computador eles podem apontar para C:\Users\teste.
set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python314\python.exe"
if exist "%PYTHON_EXE%" goto PYTHON_FOUND

set "PYTHON_EXE=%ProgramFiles%\Python314\python.exe"
if exist "%PYTHON_EXE%" goto PYTHON_FOUND

set "PYTHON_EXE=%ProgramFiles(x86)%\Python314\python.exe"
if exist "%PYTHON_EXE%" goto PYTHON_FOUND

set "PYTHON_EXE=%LOCALAPPDATA%\Microsoft\WindowsApps\python.exe"
if exist "%PYTHON_EXE%" goto PYTHON_FOUND

goto ERRO_PYTHON

:PYTHON_FOUND
echo Python encontrado:
echo %PYTHON_EXE%
"%PYTHON_EXE%" -c "import sys, encodings, venv; print(sys.version)"
if errorlevel 1 goto ERRO_PYTHON_QUEBRADO

echo.
echo Validando ambiente virtual...
if not exist "%VENV_PYTHON%" goto CREATE_VENV
"%VENV_PYTHON%" -c "import sys, encodings; print(sys.executable)" >nul 2>nul
if errorlevel 1 goto CREATE_VENV
goto INSTALL_DEPS

:CREATE_VENV
if exist ".venv" echo Removendo .venv antigo ou copiado de outro usuario...
if exist ".venv" rmdir /S /Q ".venv"

echo Criando ambiente virtual local...
"%PYTHON_EXE%" -m venv ".venv"
if errorlevel 1 goto ERRO_VENV

if not exist "%VENV_PYTHON%" goto ERRO_VENV

:INSTALL_DEPS
echo Python da .venv:
"%VENV_PYTHON%" -c "import sys; print(sys.executable)"
if errorlevel 1 goto ERRO_VENV

echo.
echo Atualizando pip...
"%VENV_PYTHON%" -m ensurepip --upgrade >nul 2>nul
"%VENV_PYTHON%" -m pip install --upgrade pip setuptools wheel
if errorlevel 1 goto ERRO_PIP

echo.
echo Preparando dependencias locais do Windows...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$lines=Get-Content -LiteralPath 'requirements.txt'; $lines | Where-Object {$_ -notmatch '^\s*(gunicorn|psycopg2-binary)\b'} | Set-Content -LiteralPath '.requirements_local.txt' -Encoding UTF8"
if errorlevel 1 goto ERRO_REQ_LOCAL

echo Instalando/verificando dependencias...
"%VENV_PYTHON%" -m pip install -r ".requirements_local.txt"
if errorlevel 1 goto ERRO_DEPS

echo.
echo Iniciando servidor local em http://127.0.0.1:%PORT%
echo Aguarde o navegador abrir. Para parar, pressione CTRL+C.
echo.

"%VENV_PYTHON%" app.py
set "APP_EXIT=%ERRORLEVEL%"
echo.
if not "%APP_EXIT%"=="0" echo O servidor encerrou com erro. Leia a mensagem acima.
if "%APP_EXIT%"=="0" echo O servidor foi encerrado.
pause
exit /b %APP_EXIT%

:ERRO_PASTA
echo ERRO: app.py nao encontrado.
echo Rode este BAT dentro da pasta orcamento-main onde fica o app.py.
pause
exit /b 1

:ERRO_REQ
echo ERRO: requirements.txt nao encontrado.
echo Rode este BAT dentro da pasta orcamento-main onde fica o requirements.txt.
pause
exit /b 1

:ERRO_PYTHON
echo ERRO: Python 3.14 nao encontrado no caminho real esperado.
echo Caminho esperado principal:
echo %LOCALAPPDATA%\Programs\Python\Python314\python.exe
echo.
echo A pasta do Menu Iniciar mostra apenas atalhos, nao o executavel real.
echo Abra o atalho Python 3.14 e rode: import sys; print^(sys.executable^)
pause
exit /b 1

:ERRO_PYTHON_QUEBRADO
echo ERRO: o Python encontrado existe, mas nao conseguiu carregar encodings ou venv.
echo Reinstale o Python 3.14 marcando pip e venv.
pause
exit /b 1

:ERRO_VENV
echo ERRO: nao foi possivel criar ou validar o ambiente virtual .venv.
echo Python usado: %PYTHON_EXE%
pause
exit /b 1

:ERRO_PIP
echo ERRO ao atualizar pip, setuptools ou wheel.
pause
exit /b 1

:ERRO_REQ_LOCAL
echo ERRO ao preparar .requirements_local.txt.
pause
exit /b 1

:ERRO_DEPS
echo ERRO ao instalar dependencias.
echo Leia a mensagem acima. Se falhar por pacote sem suporte no Python 3.14, use Python 3.12.
pause
exit /b 1
