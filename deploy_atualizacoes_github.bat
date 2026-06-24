@echo off
setlocal

cd /d "%~dp0"

set "REMOTE_URL=https://github.com/primemarbleshop/orcamento.git"
set "BRANCH=main"
set "COMMIT_MSG=Atualizar controle de vendas e relatorio"
set "GIT_EXE=C:\Program Files\Git\cmd\git.exe"

if not exist "%GIT_EXE%" (
    where git >nul 2>nul
    if errorlevel 1 (
        echo.
        echo ERRO: Git nao encontrado.
        echo Feche esta janela, abra uma nova e tente novamente.
        echo Se continuar, instale o Git for Windows.
        echo.
        pause
        exit /b 1
    )
    set "GIT_EXE=git"
)

echo Usando Git:
"%GIT_EXE%" --version

if not exist ".git" (
    echo.
    echo Inicializando repositorio Git local...
    "%GIT_EXE%" init
)

echo.
echo Configurando usuario local do Git...
"%GIT_EXE%" config user.name "primemarbleshop"
"%GIT_EXE%" config user.email "primemarbleshop@users.noreply.github.com"

"%GIT_EXE%" remote get-url origin >nul 2>nul
if errorlevel 1 (
    echo.
    echo Adicionando remoto origin...
    "%GIT_EXE%" remote add origin "%REMOTE_URL%"
) else (
    echo.
    echo Atualizando remoto origin...
    "%GIT_EXE%" remote set-url origin "%REMOTE_URL%"
)

echo.
echo Preparando branch local %BRANCH%...
"%GIT_EXE%" checkout -B %BRANCH%

echo.
echo Buscando historico atual do GitHub...
"%GIT_EXE%" fetch origin %BRANCH%
if not errorlevel 1 (
    echo Alinhando historico local com origin/%BRANCH% sem apagar seus arquivos...
    "%GIT_EXE%" reset --mixed origin/%BRANCH%
) else (
    echo Aviso: nao foi possivel buscar origin/%BRANCH%. O push pode pedir sincronizacao depois.
)

echo.
echo Adicionando SOMENTE os arquivos atualizados/adicionados...
"%GIT_EXE%" add app.py
"%GIT_EXE%" add config.py
"%GIT_EXE%" add pricing.py
"%GIT_EXE%" add README.md
"%GIT_EXE%" add run_local.bat
"%GIT_EXE%" add deploy_atualizacoes_github.bat
"%GIT_EXE%" add .env.example
"%GIT_EXE%" add .gitignore
"%GIT_EXE%" add static/css/pilot.css
"%GIT_EXE%" add static/js/configurador.js
"%GIT_EXE%" add templates/index.html
"%GIT_EXE%" add templates/login.html
"%GIT_EXE%" add templates/setup.html
"%GIT_EXE%" add templates/partials/app_header.html
"%GIT_EXE%" add templates/conversao_vendas.html
"%GIT_EXE%" add templates/relatorio_vendas.html
"%GIT_EXE%" add templates/alterar_senha.html
"%GIT_EXE%" add templates/clientes.html
"%GIT_EXE%" add templates/configuracoes.html
"%GIT_EXE%" add templates/configurador_3d.html
"%GIT_EXE%" add templates/criar_usuario.html
"%GIT_EXE%" add templates/detalhes_orcamento.html
"%GIT_EXE%" add templates/detalhes_orcamento_salvo.html
"%GIT_EXE%" add templates/detalhes_ordem_servico.html
"%GIT_EXE%" add templates/editar_cliente.html
"%GIT_EXE%" add templates/editar_material.html
"%GIT_EXE%" add templates/editar_orcamento.html
"%GIT_EXE%" add templates/editar_usuario.html
"%GIT_EXE%" add templates/gerenciar_usuarios.html
"%GIT_EXE%" add templates/materiais.html
"%GIT_EXE%" add templates/orcamentos.html
"%GIT_EXE%" add templates/orcamentos_salvos.html
"%GIT_EXE%" add templates/ordens_servico.html

echo.
echo Arquivos preparados para commit:
"%GIT_EXE%" status --short
echo.
echo Arquivos que realmente entrarao no commit:
"%GIT_EXE%" diff --cached --name-status

echo.
set /p CONFIRMAR="Confirmar commit e push desses arquivos? (S/N): "
if /I not "%CONFIRMAR%"=="S" (
    echo Operacao cancelada. Nenhum push foi feito.
    pause
    exit /b 0
)

echo.
echo Criando commit...
"%GIT_EXE%" commit -m "%COMMIT_MSG%"
if errorlevel 1 (
    echo.
    echo Nenhum commit criado ou ocorreu erro no commit.
    echo O push foi cancelado para evitar enviar sem atualizar nada.
    pause
    exit /b 1
)

echo.
echo Enviando para GitHub...
"%GIT_EXE%" push -u origin %BRANCH%
if errorlevel 1 (
    echo.
    echo ERRO ao enviar para o GitHub.
    echo.
    echo Possiveis causas:
    echo 1. Voce ainda nao fez login/autorizou o GitHub nesta maquina.
    echo 2. A branch local precisa sincronizar com o GitHub.
    echo 3. O GitHub pediu autenticacao e ela foi cancelada.
    echo.
    echo Tente abrir uma nova janela do Prompt e rode:
    echo cd /d "%~dp0"
    echo "%GIT_EXE%" pull origin %BRANCH% --allow-unrelated-histories
    echo Depois execute este BAT novamente.
    echo.
    pause
    exit /b 1
)

echo.
echo Deploy para GitHub concluido com sucesso.
echo Repositorio: %REMOTE_URL%
echo Branch: %BRANCH%
echo.
pause
