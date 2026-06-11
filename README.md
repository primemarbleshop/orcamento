# Prime Marble Shop - Orcamentos

Sistema Flask para cadastro de clientes, materiais, orcamentos, orcamentos salvos e ordens de servico.

## Rodar localmente no Windows

1. Abra o Prompt de Comando ou PowerShell.
2. Entre na pasta do projeto:

```bat
cd C:\Users\teste\Desktop\orcamento-main
```

3. Execute:

```bat
run_local.bat
```

4. Acesse no navegador:

```text
http://127.0.0.1:5000
```

O script cria um ambiente virtual `.venv`, instala as dependencias e sobe o Flask em modo de teste local.

## Banco de dados

- Localmente, o sistema usa `orcamentos.db` dentro da propria pasta do projeto.
- No Render, o sistema continua usando `/data/orcamentos.db`.
- Se quiser usar outro banco local, defina a variavel `DATABASE_PATH`.

## Variaveis uteis

Copie `.env.example` para `.env` se quiser documentar seus valores locais:

```text
SECRET_KEY=troque-esta-chave-local
HOST=127.0.0.1
PORT=5000
FLASK_DEBUG=1
```

O app tambem aceita `WHATSAPP_PHONE_ID`, `WHATSAPP_TOKEN` e `WHATSAPP_TEMPLATE_NAME` para testes de envio via WhatsApp.
