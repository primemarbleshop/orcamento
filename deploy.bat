@echo off
cd /d "C:\Users\piada\Desktop\orcamento-github"
echo.
echo === Orcamento - Deploy para GitHub ===
echo.
git add -A
git status
echo.
set /p msg="Mensagem do commit (ou Enter para 'Atualizar orcamento'): "
if "%msg%"=="" set msg=Atualizar orcamento
git commit -m "%msg%"
git push origin main
echo.
echo Deploy enviado! O Render vai atualizar automaticamente.
echo.
pause
