# ðŸ“Œ Imports de Bibliotecas Externas
import os
import sys

PROJECT_DIR = os.path.abspath(os.path.dirname(__file__))
VENV_PYTHON = os.path.join(PROJECT_DIR, ".venv", "Scripts", "python.exe")

if (
    os.name == "nt"
    and os.path.exists(VENV_PYTHON)
    and os.path.abspath(sys.executable).lower() != os.path.abspath(VENV_PYTHON).lower()
):
    os.execv(VENV_PYTHON, [VENV_PYTHON, __file__, *sys.argv[1:]])

from flask import Flask, render_template, make_response, request, redirect, url_for, jsonify, flash, session, send_file, abort
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime
from pytz import timezone
from sqlalchemy import or_, text
import io
import fitz  # PyMuPDF
import requests
import base64
import json
import subprocess
from itsdangerous import URLSafeSerializer

from models import db, Orcamento, OrcamentoSalvo, Usuario  # Modelos do SQLAlchemy
from pricing import CUBA_VALORES_PADRAO, calcular_valor_item

# 📌 Importa Configuração Externa
from config import Config

WHATSAPP_PHONE_ID = os.getenv('WHATSAPP_PHONE_ID', '')
WHATSAPP_TOKEN = os.getenv('WHATSAPP_TOKEN', '')
WHATSAPP_TEMPLATE_NAME = os.getenv('WHATSAPP_TEMPLATE_NAME', 'envio_orcamento')
VENDAS_DATA_INICIAL = datetime(2026, 6, 1)

def _formatar_telefone(telefone_cliente):
    telefone = telefone_cliente.replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
    if not telefone.startswith('55'):
        telefone = '55' + telefone
    return telefone

def _upload_media_whatsapp(pdf_bytes, filename):
    url = f'https://graph.facebook.com/v21.0/{WHATSAPP_PHONE_ID}/media'
    headers = {'Authorization': f'Bearer {WHATSAPP_TOKEN}'}
    files = {
        'file': (filename, pdf_bytes, 'application/pdf'),
        'messaging_product': (None, 'whatsapp'),
        'type': (None, 'application/pdf')
    }
    resp = requests.post(url, headers=headers, files=files, timeout=30)
    if resp.status_code == 200:
        media_id = resp.json().get('id')
        print(f'[WhatsApp] Media uploaded: {media_id}')
        return media_id
    print(f'[WhatsApp] Erro upload media {resp.status_code}: {resp.text}')
    return None

def _enviar_documento_whatsapp(telefone, media_id, filename, caption):
    url = f'https://graph.facebook.com/v21.0/{WHATSAPP_PHONE_ID}/messages'
    headers = {
        'Authorization': f'Bearer {WHATSAPP_TOKEN}',
        'Content-Type': 'application/json'
    }
    payload = {
        'messaging_product': 'whatsapp',
        'to': telefone,
        'type': 'document',
        'document': {
            'id': media_id,
            'filename': filename,
            'caption': caption
        }
    }
    resp = requests.post(url, json=payload, headers=headers, timeout=10)
    if resp.status_code == 200:
        print(f'[WhatsApp] Documento enviado para {telefone}')
        return True
    print(f'[WhatsApp] Erro envio documento {resp.status_code}: {resp.text}')
    return False

def enviar_whatsapp_orcamento(telefone_cliente, codigo_orcamento, nome_cliente='', pdf_bytes=None):
    if not WHATSAPP_PHONE_ID or not WHATSAPP_TOKEN:
        print('[WhatsApp] Token ou Phone ID não configurado, pulando envio.')
        return False
    telefone = _formatar_telefone(telefone_cliente)
    caption = f'Olá {nome_cliente or "Cliente"}, aqui está o seu orçamento {codigo_orcamento}. No que mais posso te ajudar?'
    if pdf_bytes:
        filename = f'orcamento_{codigo_orcamento}.pdf'
        media_id = _upload_media_whatsapp(pdf_bytes, filename)
        if media_id:
            return _enviar_documento_whatsapp(telefone, media_id, filename, caption)
    url = f'https://graph.facebook.com/v21.0/{WHATSAPP_PHONE_ID}/messages'
    headers = {
        'Authorization': f'Bearer {WHATSAPP_TOKEN}',
        'Content-Type': 'application/json'
    }
    payload = {
        'messaging_product': 'whatsapp',
        'to': telefone,
        'type': 'text',
        'text': {'body': caption}
    }
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        if resp.status_code == 200:
            print(f'[WhatsApp] Mensagem enviada para {telefone}')
            return True
        print(f'[WhatsApp] Erro {resp.status_code}: {resp.text}')
        return False
    except Exception as e:
        print(f'[WhatsApp] Erro ao enviar: {e}')
        return False

def _get_weasyprint_html():
    try:
        from weasyprint import HTML
        return HTML
    except OSError as exc:
        raise RuntimeError(
            "WeasyPrint precisa das bibliotecas nativas GTK/Pango instaladas para gerar PDF no Windows."
        ) from exc


def _resposta_pdf(pdf_bytes, filename):
    response = make_response(pdf_bytes)
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = f"inline; filename={filename}"
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


def _hex_para_rgb01(cor_hex):
    cor = (cor_hex or "#4e73df").strip().lstrip("#")
    if len(cor) != 6:
        cor = "4e73df"
    try:
        return tuple(int(cor[i:i + 2], 16) / 255 for i in (0, 2, 4))
    except ValueError:
        return (0.305, 0.451, 0.875)

def _moeda(valor):
    return "R$ {:,.2f}".format(float(valor or 0)).replace(",", "X").replace(".", ",").replace("X", ".")


def calcular_parcelas_orcamento(total, max_parcelas=None, valor_minimo_parcela=None):
    try:
        total = float(total or 0)
    except (TypeError, ValueError):
        total = 0
    try:
        maximo = int(max_parcelas or 10)
    except (TypeError, ValueError):
        maximo = 10
    try:
        minimo = float(valor_minimo_parcela or 100)
    except (TypeError, ValueError):
        minimo = 100

    maximo = max(1, maximo)
    if total <= 0:
        return 1
    if minimo <= 0:
        return maximo
    return max(1, min(maximo, int(total // minimo) or 1))


PAGAMENTOS_PADRAO = {
    "1": {
        "ativo": True,
        "titulo": "Cartão de Crédito",
        "descricao": "Pagamento de 100% na aprovação do orçamento",
    },
    "2": {
        "ativo": True,
        "titulo": "À vista (Dinheiro/Pix) com desconto",
        "descricao": "Sinal de 50% e 50% na entrega",
    },
    "3": {
        "ativo": True,
        "titulo": "À vista (Dinheiro/Pix) com desconto",
        "descricao": "Sinal de 80% e 20% na entrega",
    },
}


CATEGORIAS_VENDAS_PADRAO = {
    "tipos_cliente": ["Cliente de Porta", "Arquiteto", "Construtora", "Cliente Online", "Indicação"],
    "formas_pagamento": ["Débito", "Crédito", "Pix", "Dinheiro"],
}


def _bool_config(valor, padrao=True):
    if valor is None:
        return padrao
    if isinstance(valor, bool):
        return valor
    return str(valor).strip().lower() not in ("0", "false", "nao", "não", "")


def pagamentos_config_padrao(dados=None):
    dados = dados or empresa_config_dict()
    pagamentos = {}
    for chave, padrao in PAGAMENTOS_PADRAO.items():
        pagamentos[chave] = {
            "ativo": _bool_config(dados.get(f"pagamento_{chave}_ativo"), padrao["ativo"]),
            "titulo": (dados.get(f"pagamento_{chave}_titulo") or padrao["titulo"]).strip(),
            "descricao": (dados.get(f"pagamento_{chave}_descricao") or padrao["descricao"]).strip(),
        }
    return pagamentos


def pagamentos_config_orcamento(orcamento_salvo=None):
    pagamentos_atuais = pagamentos_config_padrao()
    if orcamento_salvo and getattr(orcamento_salvo, "pagamentos_config_json", None):
        try:
            salvos = json.loads(orcamento_salvo.pagamentos_config_json)
            if isinstance(salvos, dict):
                pagamentos = pagamentos_atuais.copy()
                for chave, valores in salvos.items():
                    if chave in pagamentos and isinstance(valores, dict):
                        pagamentos[chave].update({
                            "titulo": (valores.get("titulo") or pagamentos[chave]["titulo"]).strip(),
                            "descricao": (valores.get("descricao") or pagamentos[chave]["descricao"]).strip(),
                        })
                        pagamentos[chave]["ativo"] = pagamentos_atuais[chave]["ativo"]
                return pagamentos
        except (TypeError, ValueError):
            pass
    return pagamentos_atuais


def pagamentos_excluidos_padrao(dados=None):
    return ",".join(
        chave for chave, pagamento in pagamentos_config_padrao(dados).items()
        if not pagamento.get("ativo", True)
    )


def chave_ordem_tabela(ambiente_nome, descricao_nome):
    return f"{ambiente_nome or ''}||{descricao_nome or ''}"


def ordem_linhas_orcamento(orcamento_salvo):
    if not orcamento_salvo or not getattr(orcamento_salvo, "ordem_linhas_json", None):
        return {}
    try:
        dados = json.loads(orcamento_salvo.ordem_linhas_json)
        if isinstance(dados, dict):
            return {
                str(chave): [int(item_id) for item_id in valores if str(item_id).isdigit()]
                for chave, valores in dados.items()
                if isinstance(valores, list)
            }
    except (TypeError, ValueError):
        pass
    return {}


def linhas_ordenadas_por_tabela(ambientes_agrupados, orcamento_salvo):
    ordem_salva = ordem_linhas_orcamento(orcamento_salvo)
    tabelas = {}
    for ambiente_nome, descricoes in (ambientes_agrupados or {}).items():
        for descricao_nome, tipos_produtos in (descricoes or {}).items():
            chave = chave_ordem_tabela(ambiente_nome, descricao_nome)
            linhas = []
            for produtos in (tipos_produtos or {}).values():
                linhas.extend(produtos or [])

            ids_salvos = ordem_salva.get(chave, [])
            if ids_salvos:
                posicoes = {item_id: index for index, item_id in enumerate(ids_salvos)}
                linhas = sorted(
                    enumerate(linhas),
                    key=lambda item: (posicoes.get(item[1].id, len(posicoes) + item[0]), item[0])
                )
                linhas = [produto for _, produto in linhas]
            tabelas[chave] = linhas
    return tabelas


def _criar_pdf_orcamento_fallback(
    orcamento_salvo,
    orcamentos,
    ambientes_agrupados,
    valor_total_final,
    telefone_usuario,
    prazo_entrega,
    desconto_avista,
    desconto_parcelado,
    observacoes,
    exclude_payments=None,
    max_parcelas=None,
    valor_minimo_parcela=None,
    pagamentos_config=None,
):
    import fitz

    empresa = empresa_config_dict()
    pagamentos_config = pagamentos_config or pagamentos_config_padrao(empresa)
    brand = _hex_para_rgb01(empresa.get("cor_primaria"))
    exclude_payments = exclude_payments or []
    doc = fitz.open()
    page = None
    width, height = fitz.paper_size("a4")
    margin = 42
    y = 0

    def nova_pagina():
        nonlocal page, y
        page = doc.new_page(width=width, height=height)
        y = margin
        page.draw_rect(fitz.Rect(0, 0, width, 72), color=brand, fill=brand)
        logo_path = empresa_logo_path()
        if os.path.exists(logo_path):
            try:
                page.insert_image(fitz.Rect(margin, 12, margin + 72, 60), filename=logo_path, keep_proportion=True)
            except Exception:
                pass
        x_titulo = margin + 86
        page.insert_text((x_titulo, 31), empresa.get("nome_empresa") or "Sistema de Orçamento", fontsize=16, fontname="helv", color=(1, 1, 1))
        page.insert_text((x_titulo, 52), f"Orçamento {orcamento_salvo.codigo}", fontsize=10, fontname="helv", color=(1, 1, 1))
        y = 96

    def texto(txt, x=None, size=9, color=(0.12, 0.14, 0.17), bold=False, gap=14):
        nonlocal y
        if y > height - 64:
            nova_pagina()
        font = "helv"
        page.insert_text((x or margin, y), str(txt), fontsize=size, fontname=font, color=color)
        y += gap

    def linha():
        nonlocal y
        if y > height - 64:
            nova_pagina()
        page.draw_line((margin, y), (width - margin, y), color=(0.82, 0.85, 0.9), width=0.7)
        y += 12

    nova_pagina()

    cliente_nome = orcamentos[0].cliente.nome if orcamentos and orcamentos[0].cliente else orcamento_salvo.cliente_nome or "Desconhecido"
    data_txt = orcamento_salvo.data_salvo.strftime("%d/%m/%Y") if orcamento_salvo.data_salvo else ""
    texto(f"Cliente: {cliente_nome}", size=11, color=brand, gap=17)
    texto(f"Data: {data_txt}    Prazo de entrega: {prazo_entrega} dias    Telefone: {telefone_usuario or '-'}", gap=18)
    linha()

    texto("Itens do orçamento", size=12, color=brand, gap=18)
    for ambiente_nome, descricoes in ambientes_agrupados.items():
        texto(ambiente_nome, size=10, color=(0.05, 0.08, 0.14), gap=15)
        for descricao_nome, tipos in descricoes.items():
            texto(f"  {descricao_nome}", size=9, color=(0.25, 0.29, 0.36), gap=14)
            for tipo_produto, itens in tipos.items():
                for item in itens:
                    material = item.material.nome if item.material else "-"
                    qtd = item.quantidade or 1
                    medidas = f"{item.comprimento or 0:g} x {item.largura or 0:g} cm"
                    desc = f"    {tipo_produto} | {material} | {medidas} | Qtd {qtd}"
                    texto(desc[:105], gap=12)
                    texto(f"    Valor: {_moeda(item.valor_total)}", x=margin + 18, color=(0.25, 0.29, 0.36), gap=13)
        y += 4

    linha()
    texto(f"Total: {_moeda(valor_total_final)}", size=14, color=brand, gap=22)

    texto("Condições de pagamento", size=11, color=brand, gap=17)
    total = float(valor_total_final or 0)
    if pagamentos_config["1"].get("ativo", True) and "1" not in exclude_payments:
        parcelas = calcular_parcelas_orcamento(total, max_parcelas, valor_minimo_parcela)
        texto(f"{pagamentos_config['1']['titulo']}: {pagamentos_config['1']['descricao']}", gap=13)
        texto(f"Parcelado: ate {parcelas}x de {_moeda(total / max(int(parcelas), 1))}", gap=13)
    if pagamentos_config["2"].get("ativo", True) and "2" not in exclude_payments:
        valor = total * (1 - float(desconto_avista or 0) / 100)
        texto(f"{pagamentos_config['2']['titulo']}: {pagamentos_config['2']['descricao']}", gap=13)
        texto(f"Valor com desconto: {_moeda(valor)}", gap=13)
    if pagamentos_config["3"].get("ativo", True) and "3" not in exclude_payments:
        valor = total * (1 - float(desconto_parcelado or 0) / 100)
        texto(f"{pagamentos_config['3']['titulo']}: {pagamentos_config['3']['descricao']}", gap=13)
        texto(f"Valor com desconto: {_moeda(valor)}", gap=16)
    if observacoes:
        linha()
        texto("Observações", size=11, color=brand, gap=17)
        for parte in str(observacoes).splitlines() or [str(observacoes)]:
            texto(parte[:110], gap=13)

    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes

def _localizar_navegador_pdf():
    candidatos = [
        os.path.join(os.environ.get("PROGRAMFILES", ""), "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(os.environ.get("PROGRAMFILES(X86)", ""), "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(os.environ.get("PROGRAMFILES", ""), "Microsoft", "Edge", "Application", "msedge.exe"),
        os.path.join(os.environ.get("PROGRAMFILES(X86)", ""), "Microsoft", "Edge", "Application", "msedge.exe"),
    ]
    for caminho in candidatos:
        if caminho and os.path.exists(caminho):
            return caminho
    return None

def _absolutizar_assets_html(html, base_url):
    static_url = "file:///" + os.path.join(PROJECT_DIR, "static").replace("\\", "/") + "/"
    html = (
        html
        .replace('href="/static/', f'href="{static_url}')
        .replace("href='/static/", f"href='{static_url}")
        .replace('src="/static/', f'src="{static_url}')
        .replace("src='/static/", f"src='{static_url}")
    )
    base = (base_url or "").rstrip("/")
    if not base:
        return html
    return (
        html
        .replace('href="/static/', f'href="{base}/static/')
        .replace("href='/static/", f"href='{base}/static/")
        .replace('src="/static/', f'src="{base}/static/')
        .replace("src='/static/", f"src='{base}/static/")
    )

def _gerar_pdf_html_com_chrome(rendered_html, base_url):
    navegador = _localizar_navegador_pdf()
    if not navegador:
        raise RuntimeError("Chrome/Edge não encontrado para gerar PDF.")

    import tempfile
    html = _absolutizar_assets_html(rendered_html, base_url)
    temp_html_path = None
    temp_pdf_path = None
    user_data_dir = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".html", mode="w", encoding="utf-8") as temp_html:
            temp_html.write(html)
            temp_html_path = temp_html.name

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_pdf:
            temp_pdf_path = temp_pdf.name

        user_data_dir = tempfile.mkdtemp(prefix="chrome-pdf-")
        file_url = "file:///" + temp_html_path.replace("\\", "/")
        comando = [
            navegador,
            "--headless=new",
            "--disable-gpu",
            "--disable-software-rasterizer",
            "--disable-dev-shm-usage",
            "--disable-background-networking",
            "--disable-background-timer-throttling",
            "--disable-client-side-phishing-detection",
            "--disable-extensions",
            "--disable-sync",
            "--metrics-recording-only",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-features=UseSkiaRenderer,VizDisplayCompositor,CanvasOopRasterization",
            f"--user-data-dir={user_data_dir}",
            "--print-to-pdf-no-header",
            f"--print-to-pdf={temp_pdf_path}",
            file_url,
        ]
        resultado = subprocess.run(comando, capture_output=True, text=True, timeout=60)
        if resultado.returncode != 0:
            raise RuntimeError((resultado.stderr or resultado.stdout or "Falha ao gerar PDF com Chrome.").strip())
        with open(temp_pdf_path, "rb") as pdf_file:
            pdf_bytes = pdf_file.read()
        if not pdf_bytes.startswith(b"%PDF-"):
            raise RuntimeError("Chrome não retornou um PDF válido.")
        return pdf_bytes
    finally:
        for caminho in (temp_html_path, temp_pdf_path):
            if caminho and os.path.exists(caminho):
                try:
                    os.unlink(caminho)
                except OSError:
                    pass
        if user_data_dir and os.path.exists(user_data_dir):
            try:
                import shutil
                shutil.rmtree(user_data_dir, ignore_errors=True)
            except Exception:
                pass

# ðŸ“Œ Inicializa o Flask
app = Flask(__name__)
app.config.from_object(Config)  # Aplica configurações do config.py

# ðŸ“Œ Inicializa o Banco de Dados
db = SQLAlchemy(app)
migrate = Migrate(app, db)

_url_serializer = URLSafeSerializer(app.config['SECRET_KEY'], salt='orcamento-link')


@app.context_processor
def dados_usuario_layout():
    config_empresa = empresa_config_dict()
    empresa_nome = config_empresa.get("nome_empresa") or "Sistema de Orçamento"
    dados_layout = {
        "empresa_config": config_empresa,
        "empresa_nome": empresa_nome,
        "empresa_logo_url": empresa_logo_url(),
        "acessorios_texto": acessorios_texto,
        "acessorios_do_orcamento": acessorios_do_orcamento,
        "texto_saia_produto": texto_saia_produto,
        "texto_fronte_produto": texto_fronte_produto,
        "texto_cuba_produto": texto_cuba_produto,
    }
    cpf = session.get('user_cpf')
    if not cpf:
        return dados_layout

    usuario = Usuario.query.filter_by(cpf=cpf).first()
    dados_layout["usuario_display_nome"] = usuario.nome if usuario and usuario.nome else cpf
    return dados_layout

@app.after_request
def injetar_ordenacao_tabelas(response):
    if request.endpoint in {"detalhes_orcamento_salvo", "detalhes_orcamento", "gerar_pdf_orcamento"}:
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"

    if response.direct_passthrough or response.mimetype != "text/html" or response.status_code >= 300:
        return response
    if request.endpoint != "detalhes_orcamento_salvo":
        return response

    html = response.get_data(as_text=True)
    if not html or "sortable_tables.js" in html or "</body>" not in html.lower():
        return response

    css_tag = '<link rel="stylesheet" href="/static/css/sortable_tables.css">'
    js_tag = '<script src="/static/js/sortable_tables.js" defer></script>'
    lower_html = html.lower()
    head_index = lower_html.rfind("</head>")

    if head_index != -1 and "sortable_tables.css" not in html:
        html = html[:head_index] + f"    {css_tag}\n" + html[head_index:]

    body_index = html.lower().rfind("</body>")
    if body_index != -1:
        html = html[:body_index] + f"    {js_tag}\n" + html[body_index:]
        response.set_data(html)
        response.headers["Content-Length"] = str(len(response.get_data()))

    return response

def gerar_token_orcamento(codigo):
    return _url_serializer.dumps(codigo)

def decodificar_token_orcamento(token):
    try:
        return _url_serializer.loads(token)
    except Exception:
        return None

def atualizar_valor_orcamento_salvo(orcamento_salvo_id):
    """Recalcula o valor total de um orçamento salvo."""
    orcamento_salvo = OrcamentoSalvo.query.get(orcamento_salvo_id)

    if orcamento_salvo and orcamento_salvo.orcamentos_ids:
        # Obtém os IDs dos orçamentos vinculados, garantindo que sejam válidos
        orcamentos_ids = [id.strip() for id in orcamento_salvo.orcamentos_ids.split(',') if id.strip().isdigit()]

        if orcamentos_ids:
            # Busca os orçamentos no banco de dados
            orcamentos = Orcamento.query.filter(Orcamento.id.in_(orcamentos_ids)).all()

            # Soma os valores dos orçamentos individuais
            valor_total = sum(orc.valor_total for orc in orcamentos)

            # Atualiza o valor total no banco de dados
            orcamento_salvo.valor_total = valor_total
            db.session.commit()

@app.route("/upload_db", methods=["POST"])
def upload_db():
    """Endpoint para upload do banco de dados SQLite para o volume persistente no Render."""
    file = request.files.get('file')
    if file and file.filename == 'orcamentos.db':
        file.save(Config.DATABASE_PATH)
        return jsonify({"mensagem": "Banco de dados enviado com sucesso!"}), 200
    return jsonify({"erro": "Arquivo inválido!"}), 400

@app.route("/download_db")
def download_db():
    if not session.get('admin'):
        flash("Acesso restrito a administradores.", "error")
        return redirect(url_for('login'))
    import os
    if os.path.exists(Config.DATABASE_PATH):
        return send_file(Config.DATABASE_PATH, as_attachment=True, download_name='orcamentos.db')
    return jsonify({"erro": "Banco de dados não encontrado!"}), 404

br_tz = timezone('America/Sao_Paulo')

UPLOADS_DIR = os.path.join(app.root_path, 'static', 'uploads')
ALLOWED_LOGO_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}


def _logo_permitida(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_LOGO_EXTENSIONS


def formatar_telefone_br(valor):
    digitos = re.sub(r'\D', '', str(valor or ''))
    if len(digitos) == 10:
        return f"({digitos[:2]}) {digitos[2:6]}-{digitos[6:]}"
    if len(digitos) == 11:
        return f"({digitos[:2]}) {digitos[2:7]}-{digitos[7:]}"
    return str(valor or '').strip()


def _config_empresa_fallback():
    return {
        'nome_empresa': '',
        'razao_social': '',
        'documento': '',
        'telefone': '',
        'whatsapp': '',
        'endereco': '',
        'logo_filename': '',
        'logo_mime': '',
        'logo_data': '',
        'cor_primaria': '#4e73df',
        'prazo_entrega_padrao': 15,
        'desconto_avista_padrao': 5,
        'desconto_parcelado_padrao': 10,
        'observacoes_padrao': 'Medidas sujeitas a confirmação no local. Valores válidos por 7 dias.',
        'max_parcelas_padrao': 10,
        'valor_minimo_parcela': 100,
        'pagamento_1_ativo': True,
        'pagamento_1_titulo': PAGAMENTOS_PADRAO['1']['titulo'],
        'pagamento_1_descricao': PAGAMENTOS_PADRAO['1']['descricao'],
        'pagamento_2_ativo': True,
        'pagamento_2_titulo': PAGAMENTOS_PADRAO['2']['titulo'],
        'pagamento_2_descricao': PAGAMENTOS_PADRAO['2']['descricao'],
        'pagamento_3_ativo': True,
        'pagamento_3_titulo': PAGAMENTOS_PADRAO['3']['titulo'],
        'pagamento_3_descricao': PAGAMENTOS_PADRAO['3']['descricao'],
        'cooktop_valor': 50,
        'acessorios_valores_json': '',
        'vendas_tipos_cliente_json': '',
        'vendas_formas_pagamento_json': '',
        'nicho_mao_obra': 150,
        'nicho_sem_fundo_mao_obra': 150,
        'rt_percentual_padrao': 10,
        'minimo_medida_cm': 10,
        'pedra_simples_margem': 0,
        'soleira_margem': 0,
        'ilharga_margem': 0,
        'pedra_simples_com_saia_margem': 0,
        'bancada_margem_ate_1000': 30,
        'bancada_margem_ate_2000': 15,
        'bancada_margem_acima_2000': 10,
        'ilharga_bipolida_margem': 15,
        'pedra_bipolida_com_saia_margem': 15,
        'pedra_bipolida_margem': 15,
        'pedra_box_adicional': 30,
        'nicho_folga_cm': 4,
        'saia_margem': 0,
        'fronte_margem': 0,
        'alisar_margem': 0,
        'cuba_valores_json': '',
    }


def obter_config_empresa():
    try:
        config = EmpresaConfig.query.first()
        if config:
            return config
    except Exception:
        return None

    try:
        config = EmpresaConfig()
        db.session.add(config)
        db.session.commit()
        return config
    except Exception:
        db.session.rollback()
        return None


def empresa_config_dict():
    config = obter_config_empresa()
    dados = _config_empresa_fallback()
    if config:
        for chave in dados:
            dados[chave] = getattr(config, chave, dados[chave])
    dados['telefone'] = formatar_telefone_br(dados.get('telefone'))
    return dados


def empresa_logo_url(config=None):
    config = config or obter_config_empresa()
    if config and getattr(config, 'logo_data', None):
        mime = getattr(config, 'logo_mime', None) or 'image/png'
        return f"data:{mime};base64,{config.logo_data}"
    return 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="1" height="1"%3E%3C/svg%3E'


def empresa_logo_path(config=None):
    config = config or obter_config_empresa()
    if config and config.logo_filename:
        caminho = os.path.join(UPLOADS_DIR, config.logo_filename)
        if os.path.exists(caminho):
            return caminho
    return ''


def empresa_logo_data_uri(config=None):
    config = config or obter_config_empresa()
    if config and getattr(config, 'logo_data', None):
        mime = getattr(config, 'logo_mime', None) or 'image/png'
        return f"data:{mime};base64,{config.logo_data}"
    return empresa_logo_url(config)


def empresa_cuba_valores(config=None):
    valores = dict(CUBA_VALORES_PADRAO)
    config = config or obter_config_empresa()
    if config and config.cuba_valores_json:
        try:
            salvos = json.loads(config.cuba_valores_json)
            if isinstance(salvos, dict):
                valores.update({str(nome): float(valor or 0) for nome, valor in salvos.items() if str(nome).strip()})
        except (TypeError, ValueError):
            pass
    return valores


ACESSORIOS_VALORES_PADRAO = {
    "Cooktop": 50,
    "Lixeira": 0,
    "Torre de tomada": 0,
    "Calha úmida": 0,
    "Dispenser": 0,
}


def empresa_acessorios_valores(config=None):
    valores = dict(ACESSORIOS_VALORES_PADRAO)
    config = config or obter_config_empresa()
    if config and getattr(config, "acessorios_valores_json", None):
        try:
            salvos = json.loads(config.acessorios_valores_json)
            if isinstance(salvos, dict):
                valores.update({str(nome): float(valor or 0) for nome, valor in salvos.items() if str(nome).strip()})
        except (TypeError, ValueError):
            pass
    elif config and getattr(config, "cooktop_valor", None) is not None:
        valores["Cooktop"] = float(config.cooktop_valor or 0)
    return valores


def _normalizar_lista_texto(valores, padrao):
    lista = []
    for valor in valores or []:
        texto = str(valor or "").strip()
        if texto and texto not in lista:
            lista.append(texto)
    return lista or list(padrao)


def _lista_config_json(config, atributo, padrao):
    if config and getattr(config, atributo, None):
        try:
            dados = json.loads(getattr(config, atributo) or "[]")
            if isinstance(dados, list):
                return _normalizar_lista_texto(dados, padrao)
        except (TypeError, ValueError):
            pass
    return list(padrao)


def empresa_tipos_cliente(config=None):
    config = config or obter_config_empresa()
    return _lista_config_json(config, "vendas_tipos_cliente_json", CATEGORIAS_VENDAS_PADRAO["tipos_cliente"])


def empresa_formas_pagamento_vendas(config=None):
    config = config or obter_config_empresa()
    return _lista_config_json(config, "vendas_formas_pagamento_json", CATEGORIAS_VENDAS_PADRAO["formas_pagamento"])


def normalizar_acessorios(nomes, valores=None):
    valores_padrao = empresa_acessorios_valores()
    valores = valores or []
    acessorios = []
    for indice, nome in enumerate(nomes or []):
        nome_limpo = str(nome or '').strip()
        if not nome_limpo:
            continue
        try:
            valor = float(str(valores[indice]).replace(',', '.')) if indice < len(valores) and str(valores[indice]).strip() else float(valores_padrao.get(nome_limpo, 0) or 0)
        except (TypeError, ValueError):
            valor = float(valores_padrao.get(nome_limpo, 0) or 0)
        acessorios.append({"nome": nome_limpo, "valor": valor})
    return acessorios


def acessorios_do_orcamento(orcamento):
    if not orcamento:
        return []
    if getattr(orcamento, "acessorios_json", None):
        try:
            dados = json.loads(orcamento.acessorios_json)
            if isinstance(dados, list):
                return normalizar_acessorios(
                    [item.get("nome") for item in dados if isinstance(item, dict)],
                    [item.get("valor") for item in dados if isinstance(item, dict)],
                )
        except (TypeError, ValueError):
            pass
    if getattr(orcamento, "tem_cooktop", "") == "Sim":
        return [{"nome": "Cooktop", "valor": float(empresa_acessorios_valores().get("Cooktop", 50) or 0)}]
    return []


def acessorios_total(acessorios):
    return sum(float(item.get("valor") or 0) for item in (acessorios or []))


def acessorios_texto(orcamento):
    nomes = [item.get("nome") for item in acessorios_do_orcamento(orcamento) if item.get("nome")]
    return ", ".join(nomes) if nomes else "-"


TIPOS_COM_SAIA_TABELA = {"Bancada", "Lavatorio", "Ilharga", "Ilharga Bipolida", "Pedra Simples com Saia", "Pedra Bipolida com Saia"}
TIPOS_COM_FRONTE_CUBA_TABELA = {"Bancada", "Lavatorio"}


def _float_tabela(valor):
    try:
        return float(valor or 0)
    except (TypeError, ValueError):
        return 0.0


def _texto_dimensao_tabela(comprimento, largura):
    comp = _float_tabela(comprimento)
    larg = _float_tabela(largura)
    if comp <= 0 or larg <= 0:
        return ""
    return f"{comp:.1f} x {larg:.1f} cm"


def texto_saia_produto(produto):
    tipo = getattr(produto, "tipo_produto", "") or ""
    if tipo not in TIPOS_COM_SAIA_TABELA:
        return ""
    return _texto_dimensao_tabela(
        getattr(produto, "comprimento_saia", 0),
        getattr(produto, "largura_saia", 0),
    )


def texto_fronte_produto(produto):
    tipo = getattr(produto, "tipo_produto", "") or ""
    if tipo not in TIPOS_COM_FRONTE_CUBA_TABELA:
        return ""
    return _texto_dimensao_tabela(
        getattr(produto, "comprimento_fronte", 0),
        getattr(produto, "largura_fronte", 0),
    )


def texto_cuba_produto(produto):
    tipo = getattr(produto, "tipo_produto", "") or ""
    if tipo not in TIPOS_COM_FRONTE_CUBA_TABELA:
        return ""

    tipo_cuba = str(getattr(produto, "tipo_cuba", "") or "").strip()
    if not tipo_cuba or tipo_cuba == "-":
        return ""

    quantidade = getattr(produto, "quantidade_cubas", 0) or 0
    if tipo_cuba.lower() == "esculpida":
        comp = _float_tabela(getattr(produto, "comprimento_cuba", 0))
        larg = _float_tabela(getattr(produto, "largura_cuba", 0))
        prof = _float_tabela(getattr(produto, "profundidade_cuba", 0))
        if comp > 0 and larg > 0 and prof > 0:
            return f"Esculpida ({quantidade}) - {comp:.1f} x {larg:.1f} x {prof:.1f} cm"
        return f"Esculpida ({quantidade})"

    return f"{tipo_cuba} ({quantidade})"


def opcoes_precificacao_empresa(config=None):
    config = config or obter_config_empresa()
    dados = empresa_config_dict()
    return {
        'cuba_valores': empresa_cuba_valores(config),
        'cooktop_valor': float(dados.get('cooktop_valor') or 50),
        'nicho_mao_obra': float(dados.get('nicho_mao_obra') or 150),
        'nicho_sem_fundo_mao_obra': float(dados.get('nicho_sem_fundo_mao_obra') or 150),
        'minimo_medida_cm': float(dados.get('minimo_medida_cm') or 10),
        'pedra_simples_margem': float(dados.get('pedra_simples_margem') or 0),
        'soleira_margem': float(dados.get('soleira_margem') or 0),
        'ilharga_margem': float(dados.get('ilharga_margem') or 0),
        'pedra_simples_com_saia_margem': float(dados.get('pedra_simples_com_saia_margem') or 0),
        'bancada_margem_ate_1000': float(dados.get('bancada_margem_ate_1000') or 30),
        'bancada_margem_ate_2000': float(dados.get('bancada_margem_ate_2000') or 15),
        'bancada_margem_acima_2000': float(dados.get('bancada_margem_acima_2000') or 10),
        'ilharga_bipolida_margem': float(dados.get('ilharga_bipolida_margem') or 15),
        'pedra_bipolida_com_saia_margem': float(dados.get('pedra_bipolida_com_saia_margem') or 15),
        'pedra_bipolida_margem': float(dados.get('pedra_bipolida_margem') or 15),
        'pedra_box_adicional': float(dados.get('pedra_box_adicional') or 30),
        'nicho_folga_cm': float(dados.get('nicho_folga_cm') or 4),
        'saia_margem': float(dados.get('saia_margem') or 0),
        'fronte_margem': float(dados.get('fronte_margem') or 0),
        'alisar_margem': float(dados.get('alisar_margem') or 0),
    }

class Usuario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    cpf = db.Column(db.String(14), unique=True, nullable=False)
    telefone = db.Column(db.String(20), nullable=True)
    senha = db.Column(db.String(200), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    ativo = db.Column(db.Boolean, default=True, nullable=False)

    def set_senha(self, senha):
        self.senha = generate_password_hash(senha)

    def check_senha(self, senha):
        return check_password_hash(self.senha, senha)
    
class Cliente(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    endereco = db.Column(db.String(200))
    telefone = db.Column(db.String(50), nullable=True)
    documento = db.Column(db.String(50), nullable=True)
    dono = db.Column(db.String(14), nullable=False)

    __table_args__ = ()
    
class Material(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    valor = db.Column(db.Float, nullable=False)

class EmpresaConfig(db.Model):
    __tablename__ = 'empresa_config'

    id = db.Column(db.Integer, primary_key=True)
    nome_empresa = db.Column(db.String(150), default='', nullable=False)
    razao_social = db.Column(db.String(180), default='')
    documento = db.Column(db.String(30), default='')
    telefone = db.Column(db.String(30), default='')
    whatsapp = db.Column(db.String(30), default='')
    endereco = db.Column(db.String(250), default='')
    logo_filename = db.Column(db.String(180), default='')
    logo_mime = db.Column(db.String(80), default='')
    logo_data = db.Column(db.Text, default='')
    cor_primaria = db.Column(db.String(20), default='#4e73df')
    prazo_entrega_padrao = db.Column(db.Integer, default=15, nullable=False)
    desconto_avista_padrao = db.Column(db.Float, default=5, nullable=False)
    desconto_parcelado_padrao = db.Column(db.Float, default=10, nullable=False)
    observacoes_padrao = db.Column(
        db.Text,
        default='Medidas sujeitas a confirmação no local. Valores válidos por 7 dias.',
        nullable=False
    )
    max_parcelas_padrao = db.Column(db.Integer, default=10, nullable=False)
    valor_minimo_parcela = db.Column(db.Float, default=100, nullable=False)
    pagamento_1_ativo = db.Column(db.Boolean, default=True, nullable=False)
    pagamento_1_titulo = db.Column(db.String(120), default=PAGAMENTOS_PADRAO['1']['titulo'], nullable=False)
    pagamento_1_descricao = db.Column(db.Text, default=PAGAMENTOS_PADRAO['1']['descricao'], nullable=False)
    pagamento_2_ativo = db.Column(db.Boolean, default=True, nullable=False)
    pagamento_2_titulo = db.Column(db.String(120), default=PAGAMENTOS_PADRAO['2']['titulo'], nullable=False)
    pagamento_2_descricao = db.Column(db.Text, default=PAGAMENTOS_PADRAO['2']['descricao'], nullable=False)
    pagamento_3_ativo = db.Column(db.Boolean, default=True, nullable=False)
    pagamento_3_titulo = db.Column(db.String(120), default=PAGAMENTOS_PADRAO['3']['titulo'], nullable=False)
    pagamento_3_descricao = db.Column(db.Text, default=PAGAMENTOS_PADRAO['3']['descricao'], nullable=False)
    cooktop_valor = db.Column(db.Float, default=50, nullable=False)
    acessorios_valores_json = db.Column(db.Text, default='')
    vendas_tipos_cliente_json = db.Column(db.Text, default='')
    vendas_formas_pagamento_json = db.Column(db.Text, default='')
    nicho_mao_obra = db.Column(db.Float, default=150, nullable=False)
    nicho_sem_fundo_mao_obra = db.Column(db.Float, default=150, nullable=False)
    rt_percentual_padrao = db.Column(db.Float, default=10, nullable=False)
    minimo_medida_cm = db.Column(db.Float, default=10, nullable=False)
    pedra_simples_margem = db.Column(db.Float, default=0, nullable=False)
    soleira_margem = db.Column(db.Float, default=0, nullable=False)
    ilharga_margem = db.Column(db.Float, default=0, nullable=False)
    pedra_simples_com_saia_margem = db.Column(db.Float, default=0, nullable=False)
    bancada_margem_ate_1000 = db.Column(db.Float, default=30, nullable=False)
    bancada_margem_ate_2000 = db.Column(db.Float, default=15, nullable=False)
    bancada_margem_acima_2000 = db.Column(db.Float, default=10, nullable=False)
    ilharga_bipolida_margem = db.Column(db.Float, default=15, nullable=False)
    pedra_bipolida_com_saia_margem = db.Column(db.Float, default=15, nullable=False)
    pedra_bipolida_margem = db.Column(db.Float, default=15, nullable=False)
    pedra_box_adicional = db.Column(db.Float, default=30, nullable=False)
    nicho_folga_cm = db.Column(db.Float, default=4, nullable=False)
    saia_margem = db.Column(db.Float, default=0, nullable=False)
    fronte_margem = db.Column(db.Float, default=0, nullable=False)
    alisar_margem = db.Column(db.Float, default=0, nullable=False)
    cuba_valores_json = db.Column(db.Text, default='')

class Ambiente(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    dono = db.Column(db.String(14), nullable=False)
    
    __table_args__ = (db.UniqueConstraint('nome', 'dono', name='_ambiente_nome_dono_uc'),)

class Descricao(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    dono = db.Column(db.String(14), nullable=False)
    
    __table_args__ = (db.UniqueConstraint('nome', 'dono', name='_descricao_nome_dono_uc'),)

class Produto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    dono = db.Column(db.String(14), nullable=False)
    
    __table_args__ = (db.UniqueConstraint('nome', 'dono', name='_produto_nome_dono_uc'),)

class ItemRemovidoOrcamento(db.Model):
    __tablename__ = 'item_removido_orcamento'
    
    id = db.Column(db.Integer, primary_key=True)
    orcamento_salvo_codigo = db.Column(db.String, db.ForeignKey('orcamento_salvo.codigo', ondelete='CASCADE'), nullable=False)
    item_id = db.Column(db.Integer, nullable=False)
    cliente_id = db.Column(db.Integer, nullable=False)
    data_remocao = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (db.UniqueConstraint('orcamento_salvo_codigo', 'item_id', name='_unique_remocao_item'),)

class OrcamentoSalvo(db.Model):
    __tablename__ = 'orcamento_salvo'
    
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String, unique=True, nullable=False)
    orcamentos_ids = db.Column(db.Text, nullable=False)
    data_salvo = db.Column(db.DateTime, default=datetime.utcnow)
    valor_total = db.Column(db.Float, nullable=False)
    criado_por = db.Column(db.String)
    status = db.Column(db.String, default='Em Espera')
    tipo_cliente = db.Column(db.String, default='Cliente de Porta')
    valor_venda = db.Column(db.Float, nullable=True)
    forma_pagamento = db.Column(db.String(30), nullable=True)
    data_fechamento = db.Column(db.DateTime, nullable=True)
    observacao_vendas = db.Column(db.Text, nullable=True)
    entrada_percentual = db.Column(db.Float, nullable=True)
    final_percentual = db.Column(db.Float, nullable=True)
    entrada_valor = db.Column(db.Float, nullable=True)
    final_valor = db.Column(db.Float, nullable=True)
    prazo_entrega = db.Column(db.Integer, default=15, nullable=False)
    desconto_avista = db.Column(db.Integer, default=5, nullable=False)
    desconto_parcelado = db.Column(db.Integer, default=10, nullable=False)
    observacoes = db.Column(db.Text, default="Medidas sujeitas a confirmação no local. Valores válidos por 7 dias.", nullable=False)
    exclude_payments = db.Column(db.String(50), default='')
    desenhos_ordem_servico = db.relationship('DesenhoOrdemServico', backref='orcamento', lazy=True)
    desenho_ordem_servico = db.Column(db.Text, nullable=True)
    max_parcelas = db.Column(db.Integer, nullable=True)
    valor_minimo_parcela = db.Column(db.Float, nullable=True)
    pagamentos_config_json = db.Column(db.Text, default='')
    ordem_linhas_json = db.Column(db.Text, default='')

    @property
    def cliente_nome(self):
        if not self.orcamentos_ids:
            return "Não definido"

        primeiro_orcamento_id = self.orcamentos_ids.split(",")[0].strip()

        if not primeiro_orcamento_id.isdigit():
            return "Não definido"

        primeiro_orcamento = Orcamento.query.get(int(primeiro_orcamento_id))
        return primeiro_orcamento.cliente.nome if primeiro_orcamento else "Não definido"

    def gerar_codigo(self):
        ultimo_codigo = db.session.query(db.func.max(OrcamentoSalvo.codigo)).scalar()
        if not ultimo_codigo:
            novo_num = 100
        else:
            novo_num = int(ultimo_codigo[1:]) + 1
        self.codigo = f"O{novo_num:06d}"

class Orcamento(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('cliente.id'))
    cliente = db.relationship('Cliente', backref=db.backref('orcamentos', lazy=True))
    ambiente_id = db.Column(db.Integer, db.ForeignKey('ambiente.id'))
    ambiente = db.relationship('Ambiente', backref=db.backref('orcamentos', lazy=True))
    descricao_id = db.Column(db.Integer, db.ForeignKey('descricao.id'))  # NOVO CAMPO
    descricao = db.relationship('Descricao', backref=db.backref('orcamentos', lazy=True))
    produto_id = db.Column(db.Integer, db.ForeignKey('produto.id'))  # NOVO CAMPO
    produto = db.relationship('Produto', backref=db.backref('orcamentos', lazy=True))  # NOVO CAMPO
    tipo_produto = db.Column(db.String(100), nullable=False)
    material_id = db.Column(db.Integer, db.ForeignKey('material.id'))
    material = db.relationship('Material', backref=db.backref('orcamentos', lazy=True))
    quantidade = db.Column(db.Integer, nullable=False)
    comprimento = db.Column(db.Float, nullable=False)
    largura = db.Column(db.Float, nullable=False)
    instalacao = db.Column(db.String(50), default="Não")  # Sim ou Não, padrão "Não"
    instalacao_valor = db.Column(db.Float, default=0.0)   # Valor digitado
    rt = db.Column(db.String(50), default="Não")
    rt_percentual = db.Column(db.Float, default=0.0)
    valor_total = db.Column(db.Float, nullable=False, default=0.0)
    dono = db.Column(db.String(14), nullable=False)
    data = db.Column(db.DateTime, default=lambda: datetime.now(br_tz))
    
    comprimento_saia = db.Column(db.Float, default=0.0)
    largura_saia = db.Column(db.Float, default=0.0)
    comprimento_fronte = db.Column(db.Float, default=0.0)
    largura_fronte = db.Column(db.Float, default=0.0)
    tipo_cuba = db.Column(db.String(100), default="")
    quantidade_cubas = db.Column(db.Integer, default=0)
    comprimento_cuba = db.Column(db.Float, default=0.0)
    largura_cuba = db.Column(db.Float, default=0.0)
    profundidade_cuba = db.Column(db.Float, default=0.0)
    modelo_cuba = db.Column(db.String(50))
    tem_cooktop = db.Column(db.String(50), default="Não")
    acessorios_json = db.Column(db.Text, default='')
    profundidade_nicho = db.Column(db.Float, default=0.0)
    tem_fundo = db.Column(db.String(50), default="Sim")
    tem_alisar = db.Column(db.String(50), default="Não")
    largura_alisar = db.Column(db.Float, default=0.0)

class DesenhoOrdemServico(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    orcamento_salvo_codigo = db.Column(db.String, db.ForeignKey('orcamento_salvo.codigo', ondelete='CASCADE'), nullable=False)
    desenho_data = db.Column(db.Text, nullable=False)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)


def _eh_imagem_configurador(desenho_data):
    """Identifica imagens data URI legadas, que não são HTML editável da OS."""
    if not desenho_data:
        return False
    return str(desenho_data).lstrip().lower().startswith('data:image/')


def _eh_html_ordem_servico(desenho_data):
    """Retorna True somente para desenho HTML editável da tela Detalhes Ordem de Serviço."""
    if not desenho_data:
        return False
    return not _eh_imagem_configurador(desenho_data)


# Função para inicializar o banco de dados
def criar_banco():
    with app.app_context():
        db.create_all()
        _garantir_colunas_orcamento_salvo()
        _garantir_colunas_empresa_config()
        _garantir_colunas_orcamento()
        _garantir_colunas_usuario()
        _atualizar_textos_pagamento_padrao()
        _migrar_logo_arquivo_para_banco()

def _garantir_coluna(tabela, coluna, definicao):
    colunas = [
        row[1] for row in db.session.execute(text(f"PRAGMA table_info({tabela})")).fetchall()
    ]
    if coluna not in colunas:
        db.session.execute(text(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {definicao}"))
        db.session.commit()

def _garantir_colunas_orcamento_salvo():
    colunas = {
        "valor_venda": "FLOAT",
        "forma_pagamento": "VARCHAR(30)",
        "data_fechamento": "DATETIME",
        "observacao_vendas": "TEXT",
        "entrada_percentual": "FLOAT",
        "final_percentual": "FLOAT",
        "entrada_valor": "FLOAT",
        "final_valor": "FLOAT",
        "max_parcelas": "INTEGER",
        "valor_minimo_parcela": "FLOAT",
        "pagamentos_config_json": "TEXT",
        "ordem_linhas_json": "TEXT",
    }
    for coluna, definicao in colunas.items():
        _garantir_coluna("orcamento_salvo", coluna, definicao)


def _garantir_colunas_empresa_config():
    colunas = {
        "minimo_medida_cm": "FLOAT DEFAULT 10 NOT NULL",
        "pedra_simples_margem": "FLOAT DEFAULT 0 NOT NULL",
        "soleira_margem": "FLOAT DEFAULT 0 NOT NULL",
        "ilharga_margem": "FLOAT DEFAULT 0 NOT NULL",
        "pedra_simples_com_saia_margem": "FLOAT DEFAULT 0 NOT NULL",
        "bancada_margem_ate_1000": "FLOAT DEFAULT 30 NOT NULL",
        "bancada_margem_ate_2000": "FLOAT DEFAULT 15 NOT NULL",
        "bancada_margem_acima_2000": "FLOAT DEFAULT 10 NOT NULL",
        "ilharga_bipolida_margem": "FLOAT DEFAULT 15 NOT NULL",
        "pedra_bipolida_com_saia_margem": "FLOAT DEFAULT 15 NOT NULL",
        "pedra_bipolida_margem": "FLOAT DEFAULT 15 NOT NULL",
        "pedra_box_adicional": "FLOAT DEFAULT 30 NOT NULL",
        "nicho_folga_cm": "FLOAT DEFAULT 4 NOT NULL",
        "nicho_sem_fundo_mao_obra": "FLOAT DEFAULT 150 NOT NULL",
        "max_parcelas_padrao": "INTEGER DEFAULT 10 NOT NULL",
        "valor_minimo_parcela": "FLOAT DEFAULT 100 NOT NULL",
        "logo_mime": "VARCHAR(80) DEFAULT ''",
        "logo_data": "TEXT DEFAULT ''",
        "acessorios_valores_json": "TEXT DEFAULT ''",
        "vendas_tipos_cliente_json": "TEXT DEFAULT ''",
        "vendas_formas_pagamento_json": "TEXT DEFAULT ''",
        "pagamento_1_ativo": "BOOLEAN DEFAULT 1 NOT NULL",
        "pagamento_1_titulo": "VARCHAR(120) DEFAULT 'Cartão de Crédito' NOT NULL",
        "pagamento_1_descricao": "TEXT DEFAULT 'Pagamento de 100% na aprovação do orçamento' NOT NULL",
        "pagamento_2_ativo": "BOOLEAN DEFAULT 1 NOT NULL",
        "pagamento_2_titulo": "VARCHAR(120) DEFAULT 'À vista (Dinheiro/Pix) com desconto' NOT NULL",
        "pagamento_2_descricao": "TEXT DEFAULT 'Sinal de 50% e 50% na entrega' NOT NULL",
        "pagamento_3_ativo": "BOOLEAN DEFAULT 1 NOT NULL",
        "pagamento_3_titulo": "VARCHAR(120) DEFAULT 'À vista (Dinheiro/Pix) com desconto' NOT NULL",
        "pagamento_3_descricao": "TEXT DEFAULT 'Sinal de 80% e 20% na entrega' NOT NULL",
        "saia_margem": "FLOAT DEFAULT 0 NOT NULL",
        "fronte_margem": "FLOAT DEFAULT 0 NOT NULL",
        "alisar_margem": "FLOAT DEFAULT 0 NOT NULL",
    }
    for coluna, definicao in colunas.items():
        _garantir_coluna("empresa_config", coluna, definicao)


def _garantir_colunas_usuario():
    _garantir_coluna("usuario", "ativo", "BOOLEAN DEFAULT 1 NOT NULL")


def _garantir_colunas_orcamento():
    _garantir_coluna("orcamento", "acessorios_json", "TEXT DEFAULT ''")


def _atualizar_textos_pagamento_padrao():
    atualizacoes = {
        "pagamento_2_titulo": (
            "À vista (Dinheiro/Pix) com desconto",
            ["À vista - 50% entrada / 50% na entrega"],
        ),
        "pagamento_2_descricao": (
            "Sinal de 50% e 50% na entrega",
            ["50% de entrada e 50% na entrega"],
        ),
        "pagamento_3_titulo": (
            "À vista (Dinheiro/Pix) com desconto",
            ["À vista - 80% entrada / 20% na entrega"],
        ),
        "pagamento_3_descricao": (
            "Sinal de 80% e 20% na entrega",
            ["80% de entrada e 20% na entrega"],
        ),
    }
    for coluna, (novo_valor, valores_antigos) in atualizacoes.items():
        for valor_antigo in valores_antigos:
            db.session.execute(
                text(f"UPDATE empresa_config SET {coluna} = :novo WHERE {coluna} = :antigo"),
                {"novo": novo_valor, "antigo": valor_antigo},
            )
    db.session.commit()


def _mime_logo_por_extensao(caminho):
    extensao = os.path.splitext(caminho or "")[1].lower()
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }.get(extensao, "image/png")


def _migrar_logo_arquivo_para_banco():
    config = obter_config_empresa()
    if not config or getattr(config, 'logo_data', None):
        return
    caminho = empresa_logo_path(config)
    if not caminho or not os.path.exists(caminho):
        return
    try:
        with open(caminho, "rb") as arquivo:
            config.logo_data = base64.b64encode(arquivo.read()).decode("ascii")
        config.logo_mime = _mime_logo_por_extensao(caminho)
        db.session.commit()
    except OSError:
        db.session.rollback()

@app.route('/orcamento')
def configurador_3d():
    logado = 'user_cpf' in session
    return render_template('configurador_3d.html', logado=logado, empresa_logo_url=empresa_logo_url())

@app.route('/api/materiais')
def api_materiais():
    materiais = Material.query.order_by(Material.nome).all()
    return jsonify([{'id': m.id, 'nome': m.nome} for m in materiais])

def _gerar_pdf_bytes(codigo):
    import tempfile
    orcamento_salvo = OrcamentoSalvo.query.filter_by(codigo=codigo).first()
    if not orcamento_salvo:
        return None
    ids = [int(id) for id in orcamento_salvo.orcamentos_ids.split(",")]
    orcamentos = Orcamento.query.filter(Orcamento.id.in_(ids)).all()
    ambientes_agrupados = {}
    for orcamento in orcamentos:
        ambiente_nome = orcamento.ambiente.nome if orcamento.ambiente else 'Sem Ambiente'
        if ambiente_nome not in ambientes_agrupados:
            ambientes_agrupados[ambiente_nome] = {}
        descricao_nome = orcamento.descricao.nome if orcamento.descricao else 'Sem Descrição'
        if descricao_nome not in ambientes_agrupados[ambiente_nome]:
            ambientes_agrupados[ambiente_nome][descricao_nome] = {}
        tipo_produto = orcamento.tipo_produto
        if tipo_produto not in ambientes_agrupados[ambiente_nome][descricao_nome]:
            ambientes_agrupados[ambiente_nome][descricao_nome][tipo_produto] = []
        ambientes_agrupados[ambiente_nome][descricao_nome][tipo_produto].append(orcamento)
    valor_total_final = sum(o.valor_total for o in orcamentos)
    prazo_entrega = orcamento_salvo.prazo_entrega if orcamento_salvo.prazo_entrega is not None else 15
    desconto_avista = orcamento_salvo.desconto_avista if orcamento_salvo.desconto_avista is not None else 5
    desconto_parcelado = orcamento_salvo.desconto_parcelado if orcamento_salvo.desconto_parcelado is not None else 10
    observacoes = orcamento_salvo.observacoes if orcamento_salvo.observacoes is not None else "Medidas sujeitas a confirmação no local. Valores válidos por 7 dias."
    empresa = empresa_config_dict()
    max_parcelas = orcamento_salvo.max_parcelas if orcamento_salvo.max_parcelas is not None else int(empresa.get('max_parcelas_padrao') or 10)
    valor_minimo_parcela = orcamento_salvo.valor_minimo_parcela if orcamento_salvo.valor_minimo_parcela is not None else float(empresa.get('valor_minimo_parcela') or 100)
    parcelas_orcamento = calcular_parcelas_orcamento(valor_total_final, max_parcelas, valor_minimo_parcela)
    exclude_payments = orcamento_salvo.exclude_payments.split(',') if orcamento_salvo.exclude_payments else []
    pagamentos_config = pagamentos_config_orcamento(orcamento_salvo)
    rendered_html = render_template(
        "detalhes_orcamento_salvo.html",
        logo_url=empresa_logo_data_uri(),
        codigo_orcamento=orcamento_salvo.codigo,
        data_salvo=orcamento_salvo.data_salvo,
        cliente_nome=orcamentos[0].cliente.nome if orcamentos else "Desconhecido",
        orcamentos=orcamentos,
        ambientes_agrupados=ambientes_agrupados,
        valor_total_final="R$ {:,.2f}".format(valor_total_final).replace(",", "X").replace(".", ",").replace("X", "."),
        valor_total_float=valor_total_final,
        telefone_usuario="",
        prazo_entrega=prazo_entrega,
        desconto_avista=desconto_avista,
        desconto_parcelado=desconto_parcelado,
        observacoes=observacoes,
        pdf=True,
        exclude_payments=exclude_payments,
        pagamentos_config=pagamentos_config,
        max_parcelas=max_parcelas,
        valor_minimo_parcela=valor_minimo_parcela,
        parcelas_orcamento=parcelas_orcamento,
        linhas_ordenadas=linhas_ordenadas_por_tabela(ambientes_agrupados, orcamento_salvo)
    )
    with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_pdf:
        temp_pdf_path = temp_pdf.name
    _get_weasyprint_html()(string=rendered_html, base_url=request.url_root).write_pdf(temp_pdf_path)
    with open(temp_pdf_path, "rb") as f:
        pdf_bytes = f.read()
    os.unlink(temp_pdf_path)
    return pdf_bytes

@app.route('/api/configurador-orcamento', methods=['POST'])
def api_configurador_orcamento():
    try:
        cfg = request.get_json()
        if not cfg:
            return jsonify({'success': False, 'error': 'Dados inválidos'}), 400

        nome = (cfg.get('clienteNome') or '').strip()
        telefone = (cfg.get('clienteTelefone') or '').strip()
        endereco = (cfg.get('clienteEndereco') or '').strip()
        material_id = cfg.get('materialId')

        if not nome or not telefone or not material_id:
            return jsonify({'success': False, 'error': 'Nome, telefone e material são obrigatórios'}), 400

        material = Material.query.get(material_id)
        if not material:
            return jsonify({'success': False, 'error': 'Material não encontrado'}), 400

        pricing_opts = opcoes_precificacao_empresa()
        dono_cpf = session.get('user_cpf', '12233344441')

        cliente = Cliente.query.filter_by(telefone=telefone, dono=dono_cpf).first()
        if not cliente:
            cliente = Cliente(nome=nome, telefone=telefone, endereco=endereco, dono=dono_cpf)
            db.session.add(cliente)
            db.session.flush()

        orcamento_ids = []

        def get_or_create_produto(nome_prod):
            prod = Produto.query.filter_by(nome=nome_prod, dono=dono_cpf).first()
            if not prod:
                prod = Produto(nome=nome_prod, dono=dono_cpf)
                db.session.add(prod)
                db.session.flush()
            return prod.id

        def calc_saia_fronte(sides_dims, bordas_cfg, alts, saia_largs):
            comp_saia = 0
            larg_saia = 0
            comp_fronte = 0
            larg_fronte = 0
            ilhargas = []
            for side, dim in sides_dims:
                bt = bordas_cfg.get(side, 'livre')
                if bt == 'saia':
                    comp_saia += dim
                    larg_saia = max(larg_saia, saia_largs.get(side, 10))
                elif bt == 'fronte':
                    comp_fronte += dim
                    larg_fronte = max(larg_fronte, alts.get(side, 10))
                elif bt == 'ilharga':
                    ilhargas.append((side, dim, alts.get(side, 92)))
            return comp_saia, larg_saia, comp_fronte, larg_fronte, ilhargas

        def processar_produto_cfg(pcfg):
            produto = pcfg.get('produto', 'bancada')
            bordas = pcfg.get('bordas', {})
            borda_alts = pcfg.get('bordaAlts', {})
            borda_saia_larg = pcfg.get('bordaSaiaLarg', {})

            mat_id = pcfg.get('materialId', material.id)
            mat = Material.query.get(mat_id) or material

            def criar_item_p(tipo_produto, comprimento, largura, comp_saia, larg_saia, comp_fronte, larg_fronte,
                           tipo_cuba='', qtd_cubas=0, comp_cuba=0, larg_cuba=0, prof_cuba=0,
                           tem_cooktop='Não', prof_nicho=0, tem_fundo='Sim', tem_alisar='Não', larg_alisar=0,
                           produto_nome='', quantidade=1):
                comprimento_cal = max(comprimento, 10)
                largura_cal = max(largura, 10)
                valor_base = mat.valor * (comprimento_cal * largura_cal / 10000)

                if tipo_produto in ['Bancada', 'Lavatorio']:
                    if mat.valor < 1000:
                        valor_base *= 1.3
                    elif mat.valor < 2000:
                        valor_base *= 1.15
                    elif mat.valor < 1000000:
                        valor_base *= 1.1

                if tipo_produto in ['Ilharga Bipolida', 'Pedra Bipolida com Saia', 'Pedra Bipolida'] and valor_base < 1000000:
                    margem_bipolida = pricing_opts.get('ilharga_bipolida_margem', 15)
                    if tipo_produto == 'Pedra Bipolida com Saia':
                        margem_bipolida = pricing_opts.get('pedra_bipolida_com_saia_margem', 15)
                    elif tipo_produto == 'Pedra Bipolida':
                        margem_bipolida = pricing_opts.get('pedra_bipolida_margem', 15)
                    valor_base *= 1 + (float(margem_bipolida or 0) / 100)

                valor_total = valor_base

                if tipo_produto == 'Nicho':
                    comp_cal = max(comprimento, 10)
                    larg_cal = max(largura, 10)
                    prof_nicho_cal = max(prof_nicho, 10) if prof_nicho > 0 else 0
                    if tem_fundo == 'Sim':
                        area = ((comp_cal+4)*(larg_cal+4))+(((comp_cal+4)*prof_nicho_cal)*2)+(((larg_cal+4)*prof_nicho_cal)*2)
                    else:
                        area = ((comp_cal+4)+(larg_cal+4))*prof_nicho_cal*2
                    if tem_alisar == 'Sim' and larg_alisar > 0:
                        la = max(larg_alisar, 10)
                        area += ((comp_cal+(la*2))*la*2)+((larg_cal+(la*2))*la*2)
                    valor_total = (area/10000)*mat.valor + 150

                if comp_saia > 0 and larg_saia > 0:
                    cs_cal = max(comp_saia, 10)
                    ls_cal = max(larg_saia, 10)
                    valor_total += cs_cal * ls_cal * mat.valor / 10000

                if comp_fronte > 0 and larg_fronte > 0:
                    cf_cal = max(comp_fronte, 10)
                    lf_cal = max(larg_fronte, 10)
                    valor_total += cf_cal * lf_cal * mat.valor / 10000

                cubas_configuradas = pricing_opts.get('cuba_valores', {})
                tipo_cuba_cap = ''
                if tipo_cuba:
                    tipo_cuba_cap = next(
                        (nome for nome in cubas_configuradas if nome.lower() == str(tipo_cuba).lower()),
                        str(tipo_cuba).strip()
                    )
                if tipo_cuba_cap:
                    vc = cubas_configuradas.get(tipo_cuba_cap, 0)
                    valor_total += vc * max(qtd_cubas, 1)
                    if tipo_cuba_cap == 'Esculpida' and comp_cuba > 0:
                        m2_cuba = ((comp_cuba*larg_cuba*2)+(comp_cuba*2+larg_cuba*2)*prof_cuba)/10000
                        valor_total += m2_cuba * mat.valor * max(qtd_cubas, 1)

                if tem_cooktop == 'Sim':
                    valor_total += pricing_opts.get('cooktop_valor', 50)

                valor_total = calcular_valor_item(
                    tipo_produto=tipo_produto,
                    valor_material=mat.valor,
                    quantidade=max(quantidade, 1),
                    comprimento=comprimento,
                    largura=largura,
                    comprimento_saia=comp_saia,
                    largura_saia=larg_saia,
                    comprimento_fronte=comp_fronte,
                    largura_fronte=larg_fronte,
                    tipo_cuba=tipo_cuba_cap,
                    quantidade_cubas=max(qtd_cubas, 1) if tipo_cuba_cap else 0,
                    comprimento_cuba=comp_cuba,
                    largura_cuba=larg_cuba,
                    profundidade_cuba=prof_cuba,
                    modelo_cuba='Normal',
                    tem_cooktop=tem_cooktop,
                    acessorios_valor_total=0,
                    profundidade_nicho=prof_nicho,
                    tem_fundo=tem_fundo,
                    tem_alisar=tem_alisar,
                    largura_alisar=larg_alisar,
                    **pricing_opts,
                )

                prod_id = get_or_create_produto(produto_nome) if produto_nome else None

                orc = Orcamento(
                    cliente_id=cliente.id, ambiente_id=None,
                    descricao_id=None, produto_id=prod_id,
                    tipo_produto=tipo_produto, material_id=mat.id,
                    quantidade=max(quantidade, 1), comprimento=comprimento, largura=largura,
                    instalacao='Não', instalacao_valor=0, rt='Sim', rt_percentual=10,
                    comprimento_saia=comp_saia, largura_saia=larg_saia,
                    comprimento_fronte=comp_fronte, largura_fronte=larg_fronte,
                    tipo_cuba=tipo_cuba_cap,
                    quantidade_cubas=qtd_cubas,
                    comprimento_cuba=comp_cuba, largura_cuba=larg_cuba, profundidade_cuba=prof_cuba,
                    modelo_cuba='Normal',
                    tem_cooktop=tem_cooktop,
                    profundidade_nicho=prof_nicho,
                    tem_fundo=tem_fundo, tem_alisar=tem_alisar, largura_alisar=larg_alisar,
                    valor_total=valor_total, dono=dono_cpf
                )
                db.session.add(orc)
                db.session.flush()
                orcamento_ids.append(str(orc.id))

            if produto == 'bancada':
                modelo = pcfg.get('modelo', '')
                has_molhada = modelo != 'toda_seca'
                has_seca = modelo != 'toda_molhada'
                is_l = modelo.startswith('l_')

                def cubas_na_secao(*secoes):
                    if not pcfg.get('cuba'):
                        return '', 0, 0, 0, 0
                    qtd = pcfg.get('cubaQtd', 1)
                    c1_here = pcfg.get('cubaLocal') in secoes
                    c2_here = qtd >= 2 and pcfg.get('cuba2Local') in secoes
                    if c1_here and c2_here:
                        return pcfg.get('tipoCuba', ''), 2, pcfg.get('cubaComp', 0), pcfg.get('cubaLarg', 0), pcfg.get('cubaAlt', 0)
                    if c1_here:
                        return pcfg.get('tipoCuba', ''), 1, pcfg.get('cubaComp', 0), pcfg.get('cubaLarg', 0), pcfg.get('cubaAlt', 0)
                    if c2_here:
                        return pcfg.get('tipoCuba2', ''), 1, pcfg.get('cubaComp2', 0), pcfg.get('cubaLarg2', 0), pcfg.get('cubaAlt2', 0)
                    return '', 0, 0, 0, 0

                prof_m_val = pcfg.get('profMolhada', 60)
                prof_s_val = pcfg.get('profSeca', 60)
                mainD = max(prof_m_val, prof_s_val)

                # DENTE DE FUNDO PARA ORÇAMENTO
                # Quando bancadas lado a lado têm larguras/profundidades diferentes,
                # o dente é a diferença entre elas. Esse trecho deve ser cobrado no
                # mesmo acabamento do fundo e atribuído à bancada de maior largura.
                dente_fundo_molhada = 0
                dente_fundo_seca = 0
                dente_fundo_seca_esq = 0
                dente_fundo_seca_dir = 0
                dente_fundo_molhada_esq = 0
                dente_fundo_molhada_dir = 0

                def acumular_dente(prof_a, prof_b):
                    d = abs((prof_a or 0) - (prof_b or 0))
                    return d if d > 0 else 0

                if has_molhada and has_seca:
                    if modelo in ['molhada_esq_seca_dir', 'molhada_dir_seca_esq', 'l_seca_molhada', 'l_seca_molhada_seca']:
                        d = acumular_dente(prof_m_val, prof_s_val)
                        if prof_m_val > prof_s_val:
                            dente_fundo_molhada += d
                        elif prof_s_val > prof_m_val:
                            dente_fundo_seca += d
                    elif modelo == 'molhada_centro_seca_lat':
                        prof_seca_esq = pcfg.get('profSecaEsq', prof_s_val)
                        prof_seca_dir = pcfg.get('profSecaDir', prof_s_val)
                        d = acumular_dente(prof_m_val, prof_seca_esq)
                        if prof_m_val > prof_seca_esq:
                            dente_fundo_molhada += d
                        elif prof_seca_esq > prof_m_val:
                            dente_fundo_seca_esq += d
                        d = acumular_dente(prof_m_val, prof_seca_dir)
                        if prof_m_val > prof_seca_dir:
                            dente_fundo_molhada += d
                        elif prof_seca_dir > prof_m_val:
                            dente_fundo_seca_dir += d
                    elif modelo == 'seca_centro_molhada_lat':
                        prof_molhada_esq = pcfg.get('profMolhadaEsq', prof_m_val)
                        prof_molhada_dir = pcfg.get('profMolhadaDir', prof_m_val)
                        d = acumular_dente(prof_s_val, prof_molhada_esq)
                        if prof_s_val > prof_molhada_esq:
                            dente_fundo_seca += d
                        elif prof_molhada_esq > prof_s_val:
                            dente_fundo_molhada_esq += d
                        d = acumular_dente(prof_s_val, prof_molhada_dir)
                        if prof_s_val > prof_molhada_dir:
                            dente_fundo_seca += d
                        elif prof_molhada_dir > prof_s_val:
                            dente_fundo_molhada_dir += d

                if has_molhada and modelo != 'seca_centro_molhada_lat':
                    comp_m = pcfg.get('compMolhada', 120)
                    prof_m = prof_m_val
                    sides_m = [('fundo', comp_m)]
                    frente_m = comp_m
                    if is_l and modelo == 'l_seca_molhada':
                        frente_m = comp_m - pcfg.get('profL', 60)
                    sides_m.append(('frente', frente_m))
                    if modelo not in ['molhada_centro_seca_lat', 'l_seca_molhada_seca']:
                        sides_m.append(('esquerda', prof_m))
                    if not has_seca:
                        sides_m.append(('direita', prof_m))
                    if dente_fundo_molhada > 0:
                        sides_m.append(('fundo', dente_fundo_molhada))
                    cs, ls, cf, lf, _ilh = calc_saia_fronte(sides_m, bordas, borda_alts, borda_saia_larg)
                    tc, qc, cc, lc, pc = cubas_na_secao('molhada')
                    criar_item_p('Bancada', comp_m, prof_m, cs, ls, cf, lf,
                              tipo_cuba=tc, qtd_cubas=qc,
                              comp_cuba=cc, larg_cuba=lc, prof_cuba=pc,
                              produto_nome='Bancada Molhada')

                if has_seca and modelo != 'molhada_centro_seca_lat':
                    comp_s = pcfg.get('compSeca', 120)
                    prof_s = prof_s_val
                    sides_s = [('fundo', comp_s), ('frente', comp_s)]
                    if modelo not in ['seca_centro_molhada_lat', 'molhada_centro_seca_lat']:
                        sides_s.append(('direita', prof_s))
                    if not has_molhada:
                        sides_s.append(('esquerda', prof_s))
                    if dente_fundo_seca > 0:
                        sides_s.append(('fundo', dente_fundo_seca))
                    cs, ls, cf, lf, _ilh = calc_saia_fronte(sides_s, bordas, borda_alts, borda_saia_larg)
                    tc, qc, cc, lc, pc = cubas_na_secao('seca')
                    cook = 'Sim' if pcfg.get('cooktop') else 'Não'
                    criar_item_p('Bancada', comp_s, prof_s, cs, ls, cf, lf,
                              tipo_cuba=tc, qtd_cubas=qc,
                              comp_cuba=cc, larg_cuba=lc, prof_cuba=pc,
                              tem_cooktop=cook,
                              produto_nome='Bancada Seca')

                if modelo == 'molhada_centro_seca_lat':
                    cooktop_idx = pcfg.get('cooktopLocal', 0)
                    for idx, (side_key, comp_key, prof_key, nome, cuba_local) in enumerate([
                        ('esquerda', 'compSecaEsq', 'profSecaEsq', 'Bancada Seca Esquerda', 'seca_esq'),
                        ('direita', 'compSecaDir', 'profSecaDir', 'Bancada Seca Direita', 'seca_dir'),
                    ]):
                        comp_sl = pcfg.get(comp_key, pcfg.get('compSecaLat', 60))
                        prof_sl = pcfg.get(prof_key, prof_s_val)
                        sides_sl = [('fundo', comp_sl), ('frente', comp_sl), (side_key, prof_sl)]
                        dente_lateral = dente_fundo_seca_esq if side_key == 'esquerda' else dente_fundo_seca_dir
                        if dente_lateral > 0:
                            sides_sl.append(('fundo', dente_lateral))
                        cs, ls, cf, lf, _ilh = calc_saia_fronte(sides_sl, bordas, borda_alts, borda_saia_larg)
                        tc, qc, cc, lc, pc = cubas_na_secao(cuba_local)
                        cook = 'Sim' if pcfg.get('cooktop') and cooktop_idx == idx else 'Não'
                        criar_item_p('Bancada', comp_sl, prof_sl, cs, ls, cf, lf,
                                  tipo_cuba=tc, qtd_cubas=qc,
                                  comp_cuba=cc, larg_cuba=lc, prof_cuba=pc,
                                  tem_cooktop=cook,
                                  produto_nome=nome)

                if modelo == 'seca_centro_molhada_lat':
                    for side_key, comp_key, prof_key, nome, cuba_local in [
                        ('esquerda', 'compMolhadaEsq', 'profMolhadaEsq', 'Bancada Molhada Esquerda', 'molhada_esq'),
                        ('direita', 'compMolhadaDir', 'profMolhadaDir', 'Bancada Molhada Direita', 'molhada_dir'),
                    ]:
                        comp_ml = pcfg.get(comp_key, pcfg.get('compMolhadaLat', 60))
                        prof_ml = pcfg.get(prof_key, prof_m_val)
                        sides_ml = [('fundo', comp_ml), ('frente', comp_ml), (side_key, prof_ml)]
                        dente_lateral = dente_fundo_molhada_esq if side_key == 'esquerda' else dente_fundo_molhada_dir
                        if dente_lateral > 0:
                            sides_ml.append(('fundo', dente_lateral))
                        cs, ls, cf, lf, _ilh = calc_saia_fronte(sides_ml, bordas, borda_alts, borda_saia_larg)
                        tc, qc, cc, lc, pc = cubas_na_secao(cuba_local)
                        criar_item_p('Bancada', comp_ml, prof_ml, cs, ls, cf, lf,
                                  tipo_cuba=tc, qtd_cubas=qc,
                                  comp_cuba=cc, larg_cuba=lc, prof_cuba=pc,
                                  produto_nome=nome)

                if is_l:
                    comp_l = pcfg.get('compL', 120)
                    prof_l = pcfg.get('profL', 60)
                    sides_l = [('l_esquerda', prof_l), ('l_fundo', comp_l)]
                    if modelo == 'l_seca_molhada':
                        inner_h = mainD + comp_l - prof_m_val
                    else:
                        inner_h = comp_l - mainD
                    if inner_h > 0:
                        sides_l.append(('frente', inner_h))
                    cs, ls, cf, lf, _ilh = calc_saia_fronte(sides_l, bordas, borda_alts, borda_saia_larg)
                    criar_item_p('Bancada', comp_l, prof_l, cs, ls, cf, lf,
                              produto_nome='Bancada em L')

                for side_key in ['esquerda', 'direita', 'l_esquerda', 'l_fundo']:
                    if bordas.get(side_key) == 'ilharga':
                        alt = borda_alts.get(side_key, 92)
                        if side_key == 'l_fundo':
                            comp_l = pcfg.get('compL', 120)
                            saia_lesq = borda_saia_larg.get('l_esquerda', 10) if bordas.get('l_esquerda') == 'saia' else 0
                            saia_esq = borda_saia_larg.get('esquerda', 10) if bordas.get('esquerda') == 'saia' else 0
                            n_saias = (1 if saia_lesq > 0 else 0) + (1 if saia_esq > 0 else 0)
                            cs_ilh = alt * n_saias
                            ls_ilh = max(saia_lesq, saia_esq) if cs_ilh > 0 else 0
                            criar_item_p('Ilharga', comp_l, alt, cs_ilh, ls_ilh, 0, 0,
                                      produto_nome='Ilharga')
                        elif side_key == 'l_esquerda':
                            prof_l = pcfg.get('profL', 60)
                            saia_lfundo = borda_saia_larg.get('l_fundo', 10) if bordas.get('l_fundo') == 'saia' else 0
                            saia_frente = borda_saia_larg.get('frente', 10) if bordas.get('frente') == 'saia' else 0
                            n_saias = (1 if saia_lfundo > 0 else 0) + (1 if saia_frente > 0 else 0)
                            cs_ilh = alt * n_saias
                            ls_ilh = max(saia_lfundo, saia_frente) if cs_ilh > 0 else 0
                            criar_item_p('Ilharga', alt, prof_l, cs_ilh, ls_ilh, 0, 0,
                                      produto_nome='Ilharga')
                        else:
                            def profundidade_ilharga_lateral(side):
                                # A largura/profundidade da ilharga lateral deve seguir a bancada
                                # onde aquela lateral está encostada. Ex.: molhada 60 e seca 50
                                # => ilharga esquerda 60, ilharga direita 50 quando a molhada está à esquerda.
                                prof_m_base = pcfg.get('profMolhada', 60)
                                prof_s_base = pcfg.get('profSeca', 60)

                                if modelo == 'toda_molhada':
                                    return prof_m_base
                                if modelo == 'toda_seca':
                                    return prof_s_base

                                if modelo == 'molhada_esq_seca_dir':
                                    return prof_m_base if side == 'esquerda' else prof_s_base
                                if modelo == 'molhada_dir_seca_esq':
                                    return prof_s_base if side == 'esquerda' else prof_m_base

                                if modelo == 'molhada_centro_seca_lat':
                                    return pcfg.get('profSecaEsq', prof_s_base) if side == 'esquerda' else pcfg.get('profSecaDir', prof_s_base)
                                if modelo == 'seca_centro_molhada_lat':
                                    return pcfg.get('profMolhadaEsq', prof_m_base) if side == 'esquerda' else pcfg.get('profMolhadaDir', prof_m_base)

                                # Modelos em L: a lateral externa padrão acompanha a peça seca do braço/lateral.
                                # As laterais específicas do L continuam tratadas em l_esquerda/l_fundo acima.
                                if modelo in ['l_seca_molhada', 'l_seca_molhada_seca']:
                                    if side == 'esquerda':
                                        return pcfg.get('profL', prof_s_base)
                                    return prof_s_base if has_seca else prof_m_base

                                return prof_m_base if has_molhada else prof_s_base

                            prof_ilh = profundidade_ilharga_lateral(side_key)
                            saia_frente = borda_saia_larg.get('frente', 10) if bordas.get('frente') in ['saia'] else 0
                            saia_fundo = borda_saia_larg.get('fundo', 10) if bordas.get('fundo') in ['saia'] else 0
                            n_saias = (1 if saia_frente > 0 else 0) + (1 if saia_fundo > 0 else 0)
                            cs_ilh = alt * n_saias
                            ls_ilh = max(saia_frente, saia_fundo) if cs_ilh > 0 else 0
                            criar_item_p('Ilharga', alt, prof_ilh, cs_ilh, ls_ilh, 0, 0,
                                      produto_nome='Ilharga')

                for side_key in ['frente', 'fundo']:
                    if bordas.get(side_key) == 'ilharga':
                        alt = borda_alts.get(side_key, 92)
                        comp_total = 0
                        if has_molhada:
                            comp_total += pcfg.get('compMolhada', 120)
                        if has_seca:
                            comp_total += pcfg.get('compSeca', 120)
                        if not comp_total:
                            comp_total = 120
                        saia_esq = borda_saia_larg.get('esquerda', 10) if bordas.get('esquerda') == 'saia' else 0
                        saia_dir = borda_saia_larg.get('direita', 10) if bordas.get('direita') == 'saia' else 0
                        n_saias = (1 if saia_esq > 0 else 0) + (1 if saia_dir > 0 else 0)
                        cs_ilh = alt * n_saias
                        ls_ilh = max(saia_esq, saia_dir) if cs_ilh > 0 else 0
                        criar_item_p('Ilharga', comp_total, alt, cs_ilh, ls_ilh, 0, 0,
                                  produto_nome='Ilharga')

            elif produto == 'lavatorio':
                comp = pcfg.get('compGen', 120)
                prof = pcfg.get('profGen', 55)
                lav_modelo = pcfg.get('lavModelo', 'retangular')
                if lav_modelo == 'violao':
                    rec_larg = pcfg.get('lavRecorteLarg', 70)
                    rec_alt = pcfg.get('lavRecorteAlt', 35)
                    espelhar = pcfg.get('espelhar', False)
                    if espelhar:
                        esq_dim = prof - rec_alt
                        dir_dim = prof
                    else:
                        esq_dim = prof
                        dir_dim = prof - rec_alt
                    lav_sides = [
                        ('fundo', comp),
                        ('frente', comp),
                        ('esquerda', esq_dim),
                        ('direita', dir_dim),
                        ('direita2', rec_alt),
                    ]
                else:
                    lav_sides = [('fundo', comp), ('frente', comp), ('esquerda', prof), ('direita', prof)]
                cs, ls, cf, lf, _ilh = calc_saia_fronte(lav_sides, bordas, borda_alts, borda_saia_larg)
                tc = pcfg.get('tipoCuba', '') if pcfg.get('cuba') else ''
                qc = pcfg.get('cubaQtd', 1) if tc else 0
                lav_modelo = pcfg.get('lavModelo', 'retangular')
                lav_nome = 'Lavatorio Violao' if lav_modelo == 'violao' else 'Lavatorio Retangular'
                criar_item_p('Lavatorio', comp, prof, cs, ls, cf, lf,
                          tipo_cuba=tc, qtd_cubas=qc,
                          comp_cuba=pcfg.get('cubaComp',0), larg_cuba=pcfg.get('cubaLarg',0), prof_cuba=pcfg.get('cubaAlt',0),
                          produto_nome=lav_nome)

                if lav_modelo != 'violao':
                    for side_key in ['esquerda', 'direita']:
                        if bordas.get(side_key) == 'ilharga':
                            alt = borda_alts.get(side_key, 92)
                            saia_frente = borda_saia_larg.get('frente', 10) if bordas.get('frente') == 'saia' else 0
                            saia_fundo = borda_saia_larg.get('fundo', 10) if bordas.get('fundo') == 'saia' else 0
                            n_saias = (1 if saia_frente > 0 else 0) + (1 if saia_fundo > 0 else 0)
                            cs_ilh = alt * n_saias
                            ls_ilh = max(saia_frente, saia_fundo) if cs_ilh > 0 else 0
                            criar_item_p('Ilharga', alt, prof, cs_ilh, ls_ilh, 0, 0,
                                      produto_nome='Ilharga')

                    for side_key in ['frente', 'fundo']:
                        if bordas.get(side_key) == 'ilharga':
                            alt = borda_alts.get(side_key, 92)
                            saia_esq = borda_saia_larg.get('esquerda', 10) if bordas.get('esquerda') == 'saia' else 0
                            saia_dir = borda_saia_larg.get('direita', 10) if bordas.get('direita') == 'saia' else 0
                            n_saias = (1 if saia_esq > 0 else 0) + (1 if saia_dir > 0 else 0)
                            cs_ilh = alt * n_saias
                            ls_ilh = max(saia_esq, saia_dir) if cs_ilh > 0 else 0
                            criar_item_p('Ilharga', comp, alt, cs_ilh, ls_ilh, 0, 0,
                                      produto_nome='Ilharga')

            elif produto == 'nicho':
                criar_item_p('Nicho', pcfg.get('nichoLarg', 60), pcfg.get('nichoAlt', 30), 0, 0, 0, 0,
                           prof_nicho=pcfg.get('nichoProf', 12),
                           tem_fundo='Sim' if pcfg.get('nichoFundo', True) else 'Não',
                           tem_alisar='Sim' if pcfg.get('nichoAlisar', False) else 'Não',
                           larg_alisar=pcfg.get('nichoAlisarMedida', 0),
                           produto_nome='Nicho')

            elif produto == 'soleira':
                soleiras_list = pcfg.get('soleiras')
                if soleiras_list and isinstance(soleiras_list, list):
                    for s in soleiras_list:
                        qtd = int(s.get('qtd', 1))
                        criar_item_p('Soleira', s.get('larg', 80), s.get('prof', 15), 0, 0, 0, 0,
                                   produto_nome='Soleira', quantidade=qtd)
                else:
                    qtd_soleira = int(pcfg.get('soleiraQtd', 1))
                    criar_item_p('Soleira', pcfg.get('soleiraLarg', 80), pcfg.get('soleiraProf', 15), 0, 0, 0, 0,
                               produto_nome='Soleira', quantidade=qtd_soleira)

        processar_produto_cfg(cfg)

        for extra in cfg.get('produtosExtras', []):
            if extra.get('produto'):
                processar_produto_cfg(extra)

        if not orcamento_ids:
            return jsonify({'success': False, 'error': 'Nenhum item gerado'}), 400

        empresa = empresa_config_dict()
        orc_salvo = OrcamentoSalvo(
            orcamentos_ids=','.join(orcamento_ids),
            valor_total=sum(Orcamento.query.get(int(i)).valor_total for i in orcamento_ids),
            criado_por='Configurador Online',
            tipo_cliente='Cliente Online',
            prazo_entrega=int(empresa.get('prazo_entrega_padrao') or 15),
            desconto_avista=float(empresa.get('desconto_avista_padrao') or 5),
            desconto_parcelado=float(empresa.get('desconto_parcelado_padrao') or 10),
            observacoes=empresa.get('observacoes_padrao') or _config_empresa_fallback()['observacoes_padrao'],
            exclude_payments=pagamentos_excluidos_padrao(empresa),
            max_parcelas=int(empresa.get('max_parcelas_padrao') or 10),
            valor_minimo_parcela=float(empresa.get('valor_minimo_parcela') or 100),
            pagamentos_config_json=json.dumps(pagamentos_config_padrao(empresa), ensure_ascii=False),
        )
        orc_salvo.gerar_codigo()
        db.session.add(orc_salvo)
        db.session.flush()

        todos_desenhos = []
        for extra in cfg.get('produtosExtras', []):
            d = extra.get('desenho', '')
            if d:
                todos_desenhos.append(d)
        desenho_data = cfg.get('desenho', '')
        if desenho_data:
            todos_desenhos.append(desenho_data)
        for dd in todos_desenhos:
            desenho = DesenhoOrdemServico(
                orcamento_salvo_codigo=orc_salvo.codigo,
                desenho_data=dd
            )
            db.session.add(desenho)

        db.session.commit()

        token = gerar_token_orcamento(orc_salvo.codigo)
        return jsonify({'success': True, 'codigo': orc_salvo.codigo, 'token': token})

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

WHATSAPP_VERIFY_TOKEN = os.getenv('WHATSAPP_VERIFY_TOKEN', 'primemarble2026')

@app.route('/webhook/whatsapp', methods=['GET'])
def whatsapp_webhook_verify():
    mode = request.args.get('hub.mode')
    token = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')
    if mode == 'subscribe' and token == WHATSAPP_VERIFY_TOKEN:
        return challenge, 200
    return 'Forbidden', 403

@app.route('/webhook/whatsapp', methods=['POST'])
def whatsapp_webhook_receive():
    return jsonify({'status': 'ok'}), 200

def _ver_desenho_legado_desativado(codigo):
    abort(404)
    desenhos = [
        d for d in DesenhoOrdemServico.query.filter_by(
            orcamento_salvo_codigo=codigo
        ).order_by(DesenhoOrdemServico.data_criacao.asc()).all()
        if _eh_imagem_configurador(d.desenho_data)
    ]
    if not desenhos:
        return 'Desenho legado nao encontrado', 404

    orc_salvo = OrcamentoSalvo.query.filter_by(codigo=codigo).first()
    header_html = ''
    if orc_salvo:
        from markupsafe import escape
        cliente = escape(orc_salvo.cliente_nome or 'Não definido')
        status = escape(orc_salvo.status or '')
        tipo = escape(orc_salvo.tipo_cliente or '')
        data = orc_salvo.data_salvo.strftime('%d/%m/%Y %H:%M') if orc_salvo.data_salvo else ''
        valor = f'R$ {orc_salvo.valor_total:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.') if orc_salvo.valor_total else ''

        telefone = ''
        endereco = ''
        if orc_salvo.orcamentos_ids:
            pid = orc_salvo.orcamentos_ids.split(",")[0].strip()
            if pid.isdigit():
                po = Orcamento.query.get(int(pid))
                if po and po.cliente:
                    telefone = escape(po.cliente.telefone or '')
                    endereco = escape(po.cliente.endereco or '')

        header_html = f'''<div style="background:#12122a;padding:16px 24px;border-bottom:1px solid #2a2a4a;font-family:Arial,sans-serif;color:#ccc;display:flex;flex-wrap:wrap;gap:8px 24px;align-items:center">
  <span style="color:#fede27;font-weight:700;font-size:18px">{codigo}</span>
  <span>Cliente: <b style="color:#fff">{cliente}</b></span>
  {'<span>Tel: '+str(telefone)+'</span>' if telefone else ''}
  {'<span>End: '+str(endereco)+'</span>' if endereco else ''}
  <span>Tipo: {tipo}</span>
  <span>Data: {data}</span>
  <span>Valor: <b style="color:#fede27">{valor}</b></span>
  <span style="background:#2a2a4a;padding:2px 10px;border-radius:4px">{status}</span>
</div>'''

    total = len(desenhos)
    pages_html = ''
    for i, d in enumerate(desenhos):
        num = i + 1
        label = f'<div style="color:#888;font-size:14px;text-align:center;padding:12px 0 4px;font-family:Arial,sans-serif">Plano {num} de {total}</div>' if total > 1 else ''
        pages_html += f'{label}<div class="img-wrap"><img src="{d.desenho_data}" alt="Desenho {codigo} - {num}"></div>'

    return f'''<!DOCTYPE html>
<html><head><title>Desenho - {codigo}</title>
<style>body{{margin:0;background:#1a1a2e;display:flex;flex-direction:column;min-height:100vh}}
.img-wrap{{display:flex;justify-content:center;align-items:center;min-height:calc(100vh - 80px);padding:16px 0}}
img{{max-width:95vw;max-height:90vh;border-radius:8px;box-shadow:0 4px 20px rgba(0,0,0,.5)}}</style></head>
<body>{header_html}{pages_html}</body></html>'''

@app.route('/')
def index():
    if 'user_cpf' not in session:
        return redirect(url_for('login'))

    try:
        limite_recentes = max(int(request.args.get("limite", 6)), 6)
    except ValueError:
        limite_recentes = 6

    hoje = datetime.now(br_tz)
    orcamentos, mes_atual, ano_atual = _filtrar_orcamentos_por_periodo(
        _orcamentos_salvos_visiveis(),
        mes=hoje.month,
        ano=hoje.year,
    )
    dashboard = _montar_dashboard_vendas(orcamentos, limite_recentes=limite_recentes)
    meses = {
        1: "Janeiro",
        2: "Fevereiro",
        3: "Março",
        4: "Abril",
        5: "Maio",
        6: "Junho",
        7: "Julho",
        8: "Agosto",
        9: "Setembro",
        10: "Outubro",
        11: "Novembro",
        12: "Dezembro",
    }

    return render_template(
        'index.html',
        dashboard=dashboard,
        periodo_label=f"{meses[mes_atual]} de {ano_atual}",
        proximo_limite=limite_recentes + 6,
    )

def _ids_orcamento_salvo(orcamento_salvo):
    ids = []
    for item in (orcamento_salvo.orcamentos_ids or "").split(","):
        item = item.strip()
        if item.isdigit():
            ids.append(int(item))
    return ids

def _cliente_do_orcamento_salvo(orcamento_salvo):
    ids = _ids_orcamento_salvo(orcamento_salvo)
    if not ids:
        return None
    primeiro_orcamento = Orcamento.query.get(ids[0])
    return primeiro_orcamento.cliente if primeiro_orcamento else None

def _orcamentos_salvos_visiveis():
    user_cpf = session.get("user_cpf")
    is_admin = session.get("admin")
    orcamentos = OrcamentoSalvo.query.order_by(OrcamentoSalvo.data_salvo.desc()).all()

    if is_admin:
        return orcamentos

    visiveis = []
    for orcamento_salvo in orcamentos:
        cliente = _cliente_do_orcamento_salvo(orcamento_salvo)
        if cliente and cliente.dono == user_cpf:
            visiveis.append(orcamento_salvo)
    return visiveis

def _moeda(valor):
    return "R$ {:,.2f}".format(valor or 0).replace(",", "X").replace(".", ",").replace("X", ".")

def _valor_venda_considerado(orcamento):
    if (orcamento.status or "") == "Aprovado" and orcamento.valor_venda:
        return orcamento.valor_venda
    return orcamento.valor_total or 0

def _float_payload(valor):
    if valor in (None, ""):
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    valor = str(valor).strip().replace("R$", "").replace(" ", "")
    if "," in valor and "." in valor:
        valor = valor.replace(".", "").replace(",", ".")
    else:
        valor = valor.replace(",", ".")
    return float(valor) if valor else None

def _data_payload(valor):
    if valor in (None, ""):
        return None
    return datetime.strptime(str(valor), "%Y-%m-%d")

def _dados_venda_orcamento(orcamento):
    valor_base = orcamento.valor_venda if orcamento.valor_venda is not None else (orcamento.valor_total or 0)
    entrada_percentual = orcamento.entrada_percentual if orcamento.entrada_percentual is not None else 50
    final_percentual = orcamento.final_percentual if orcamento.final_percentual is not None else 50
    entrada_valor = orcamento.entrada_valor if orcamento.entrada_valor is not None else valor_base * entrada_percentual / 100
    final_valor = orcamento.final_valor if orcamento.final_valor is not None else valor_base * final_percentual / 100
    return {
        "valor_venda": valor_base,
        "valor_venda_formatado": _moeda(valor_base),
        "forma_pagamento": orcamento.forma_pagamento or "",
        "data_fechamento": orcamento.data_fechamento.strftime("%Y-%m-%d") if orcamento.data_fechamento else "",
        "data_fechamento_formatada": orcamento.data_fechamento.strftime("%d/%m/%Y") if orcamento.data_fechamento else "",
        "observacao_vendas": orcamento.observacao_vendas or "",
        "entrada_percentual": entrada_percentual,
        "final_percentual": final_percentual,
        "entrada_valor": entrada_valor,
        "final_valor": final_valor,
        "entrada_valor_formatado": _moeda(entrada_valor),
        "final_valor_formatado": _moeda(final_valor),
    }

def _montar_dashboard_vendas(orcamentos, limite_recentes=6):
    hoje = datetime.now(br_tz).date()
    total = len(orcamentos)
    aprovados = [o for o in orcamentos if (o.status or "") == "Aprovado"]
    espera = [o for o in orcamentos if (o.status or "") == "Em Espera"]
    declinados = [o for o in orcamentos if (o.status or "") == "Declinado"]
    valor_total = sum(o.valor_total or 0 for o in orcamentos)
    valor_aberto = sum(o.valor_total or 0 for o in espera)
    valor_aprovado = sum(_valor_venda_considerado(o) for o in aprovados)
    total_decidido = len(aprovados) + len(declinados)
    taxa_conversao = round((len(aprovados) / total_decidido) * 100, 1) if total_decidido else 0

    recentes = []
    for orcamento in orcamentos[:limite_recentes]:
        cliente = _cliente_do_orcamento_salvo(orcamento)
        data_salvo = orcamento.data_salvo
        data_base = data_salvo.date() if data_salvo else hoje
        dados_venda = _dados_venda_orcamento(orcamento)
        recentes.append({
            "id": orcamento.id,
            "codigo": orcamento.codigo,
            "cliente": cliente.nome if cliente else "Não definido",
            "valor": _moeda(orcamento.valor_total),
            "valor_float": orcamento.valor_total or 0,
            "status": orcamento.status or "Em Espera",
            "tipo_cliente": orcamento.tipo_cliente or "Cliente de Porta",
            "criado_por": orcamento.criado_por or "",
            "data": data_salvo.strftime("%d/%m/%Y") if data_salvo else "",
            "dias": max((hoje - data_base).days, 0),
            **dados_venda,
        })

    return {
        "total": total,
        "aprovados": len(aprovados),
        "espera": len(espera),
        "declinados": len(declinados),
        "decididos": total_decidido,
        "taxa_conversao": taxa_conversao,
        "valor_total": _moeda(valor_total),
        "valor_aberto": _moeda(valor_aberto),
        "valor_aprovado": _moeda(valor_aprovado),
        "ticket_medio": _moeda(valor_total / total if total else 0),
        "recentes": recentes,
    }

def _filtrar_orcamentos_por_periodo(orcamentos, mes=None, ano=None):
    try:
        mes = int(mes) if mes not in (None, "", "todos") else None
    except ValueError:
        mes = None

    try:
        ano = int(ano) if ano not in (None, "", "todos") else None
    except ValueError:
        ano = None

    filtrados = []
    data_minima = VENDAS_DATA_INICIAL.date()
    for orcamento in orcamentos:
        status = orcamento.status or "Em Espera"
        if status == "Em Espera":
            data_criacao = orcamento.data_salvo.date() if orcamento.data_salvo else None
            if data_criacao and data_criacao < data_minima:
                continue
            filtrados.append(orcamento)
            continue

        data_base = orcamento.data_fechamento or orcamento.data_salvo
        if not data_base:
            continue
        if data_base.date() < data_minima:
            continue
        if ano and data_base.year != ano:
            continue
        if mes and data_base.month != mes:
            continue
        filtrados.append(orcamento)
    return filtrados, mes, ano

@app.route('/conversao_vendas')
def conversao_vendas():
    if 'user_cpf' not in session:
        return redirect(url_for('login'))

    todos_orcamentos = _orcamentos_salvos_visiveis()
    hoje = datetime.now(br_tz)
    anos_base = set(range(VENDAS_DATA_INICIAL.year, hoje.year + 1))
    anos_disponiveis = sorted(
        anos_base | {o.data_fechamento.year for o in todos_orcamentos if o.data_fechamento},
        reverse=True,
    )
    mes_filtro = request.args.get("mes", str(hoje.month))
    ano_filtro = request.args.get("ano", str(hoje.year))
    vendedor_filtro = request.args.get("vendedor", "Todos")
    usuarios = Usuario.query.order_by(Usuario.nome).all() if session.get("admin") else []
    if session.get("admin") and vendedor_filtro and vendedor_filtro != "Todos":
        todos_orcamentos = [
            orcamento for orcamento in todos_orcamentos
            if (orcamento.criado_por or "") == vendedor_filtro
        ]
    orcamentos, mes_filtro, ano_filtro = _filtrar_orcamentos_por_periodo(
        todos_orcamentos,
        mes=mes_filtro,
        ano=ano_filtro,
    )
    dashboard = _montar_dashboard_vendas(orcamentos)
    meses = [
        (1, "Janeiro"),
        (2, "Fevereiro"),
        (3, "Março"),
        (4, "Abril"),
        (5, "Maio"),
        (6, "Junho"),
        (7, "Julho"),
        (8, "Agosto"),
        (9, "Setembro"),
        (10, "Outubro"),
        (11, "Novembro"),
        (12, "Dezembro"),
    ]
    periodo_label = "Todo o período"
    if mes_filtro and ano_filtro:
        periodo_label = f"{dict(meses).get(mes_filtro, '')} de {ano_filtro}"
    elif mes_filtro:
        periodo_label = dict(meses).get(mes_filtro, "Mês selecionado")
    elif ano_filtro:
        periodo_label = str(ano_filtro)

    return render_template(
        'conversao_vendas.html',
        dashboard=dashboard,
        meses=meses,
        anos_disponiveis=anos_disponiveis,
        filtro_mes=mes_filtro,
        filtro_ano=ano_filtro,
        usuarios=usuarios,
        vendedor_filtro=vendedor_filtro,
        periodo_label=periodo_label,
        vendas_tipos_cliente=empresa_tipos_cliente(),
        vendas_formas_pagamento=empresa_formas_pagamento_vendas(),
        orcamentos=dashboard["recentes"] if request.args.get("recentes") else [
            {
                "id": o.id,
                "codigo": o.codigo,
                "cliente": (_cliente_do_orcamento_salvo(o).nome if _cliente_do_orcamento_salvo(o) else "Não definido"),
                "valor": _moeda(o.valor_total),
                "valor_float": o.valor_total or 0,
                "status": o.status or "Em Espera",
                "tipo_cliente": o.tipo_cliente or "Cliente de Porta",
                "criado_por": o.criado_por or "",
                "data": o.data_salvo.strftime("%d/%m/%Y") if o.data_salvo else "",
                "data_salvo_iso": o.data_salvo.strftime("%Y-%m-%d") if o.data_salvo else "",
                **_dados_venda_orcamento(o),
            }
            for o in orcamentos
        ],
    )

@app.route('/relatorio_vendas')
def relatorio_vendas():
    if 'user_cpf' not in session:
        return redirect(url_for('login'))

    todos_orcamentos = _orcamentos_salvos_visiveis()
    hoje = datetime.now(br_tz)
    mes_filtro = request.args.get("mes", str(hoje.month))
    ano_filtro = request.args.get("ano", str(hoje.year))
    vendedor_filtro = request.args.get("vendedor", "Todos")
    status_filtro = request.args.get("status", "Todos")
    usuarios = Usuario.query.order_by(Usuario.nome).all() if session.get("admin") else []
    if session.get("admin") and vendedor_filtro and vendedor_filtro != "Todos":
        todos_orcamentos = [
            orcamento for orcamento in todos_orcamentos
            if (orcamento.criado_por or "") == vendedor_filtro
        ]
    orcamentos, mes_filtro, ano_filtro = _filtrar_orcamentos_por_periodo(
        todos_orcamentos,
        mes=mes_filtro,
        ano=ano_filtro,
    )
    orcamentos_detalhe = orcamentos
    if status_filtro and status_filtro != "Todos":
        orcamentos_detalhe = [
            orcamento for orcamento in orcamentos
            if (orcamento.status or "Em Espera") == status_filtro
        ]
    dashboard = _montar_dashboard_vendas(orcamentos, limite_recentes=len(orcamentos) or 1)
    detalhe_dashboard = _montar_dashboard_vendas(orcamentos_detalhe, limite_recentes=len(orcamentos_detalhe) or 1)
    meses = [
        (1, "Janeiro"), (2, "Fevereiro"), (3, "Março"), (4, "Abril"),
        (5, "Maio"), (6, "Junho"), (7, "Julho"), (8, "Agosto"),
        (9, "Setembro"), (10, "Outubro"), (11, "Novembro"), (12, "Dezembro"),
    ]
    periodo_label = "Todo o período"
    if mes_filtro and ano_filtro:
        periodo_label = f"{dict(meses).get(mes_filtro, '')} de {ano_filtro}"
    elif mes_filtro:
        periodo_label = dict(meses).get(mes_filtro, "Mês selecionado")
    elif ano_filtro:
        periodo_label = str(ano_filtro)

    status_resumo = {
        "Em Espera": {"quantidade": 0, "valor": 0},
        "Aprovado": {"quantidade": 0, "valor": 0},
        "Declinado": {"quantidade": 0, "valor": 0},
    }
    formas_pagamento = {}
    vendedores = {}
    tipos_cliente = {}
    clientes_resumo = {}

    for orcamento in orcamentos:
        status = orcamento.status or "Em Espera"
        if status not in status_resumo:
            status_resumo[status] = {"quantidade": 0, "valor": 0}
        status_resumo[status]["quantidade"] += 1
        status_resumo[status]["valor"] += _valor_venda_considerado(orcamento) if status == "Aprovado" else (orcamento.valor_total or 0)

        if (orcamento.status or "") == "Aprovado":
            valor_venda = _valor_venda_considerado(orcamento)
            forma = orcamento.forma_pagamento or "Não informado"
            vendedor = orcamento.criado_por or "Não informado"
            tipo_cliente = orcamento.tipo_cliente or "Não informado"
            cliente = _cliente_do_orcamento_salvo(orcamento)
            cliente_nome = cliente.nome if cliente else "Não informado"

            for grupo, chave in (
                (formas_pagamento, forma),
                (vendedores, vendedor),
                (tipos_cliente, tipo_cliente),
                (clientes_resumo, cliente_nome),
            ):
                if chave not in grupo:
                    grupo[chave] = {"quantidade": 0, "valor": 0}
                grupo[chave]["quantidade"] += 1
                grupo[chave]["valor"] += valor_venda

    for grupo in (formas_pagamento, vendedores, tipos_cliente, clientes_resumo):
        for item in grupo.values():
            item["ticket"] = item["valor"] / item["quantidade"] if item["quantidade"] else 0

    formas_pagamento = dict(
        sorted(formas_pagamento.items(), key=lambda item: item[1]["valor"], reverse=True)
    )
    vendedores = dict(
        sorted(vendedores.items(), key=lambda item: item[1]["valor"], reverse=True)
    )
    tipos_cliente = dict(
        sorted(tipos_cliente.items(), key=lambda item: item[1]["valor"], reverse=True)
    )
    clientes_resumo = dict(
        sorted(clientes_resumo.items(), key=lambda item: item[1]["valor"], reverse=True)[:3]
    )
    aprovados = status_resumo.get("Aprovado", {"quantidade": 0, "valor": 0})
    declinados = status_resumo.get("Declinado", {"quantidade": 0, "valor": 0})
    em_espera = status_resumo.get("Em Espera", {"quantidade": 0, "valor": 0})
    decisoes = aprovados["quantidade"] + declinados["quantidade"]
    taxa_ganho = round((aprovados["quantidade"] / decisoes) * 100, 1) if decisoes else 0
    ticket_vendas = aprovados["valor"] / aprovados["quantidade"] if aprovados["quantidade"] else 0
    observacoes_count = sum(1 for o in orcamentos if getattr(o, "observacao_vendas", None))
    usuario_atual = Usuario.query.filter_by(cpf=session.get("user_cpf")).first()
    responsavel_relatorio = usuario_atual.nome if usuario_atual and usuario_atual.nome else session.get("user_cpf", "")
    resumo_executivo = {
        "periodo": periodo_label,
        "emitido_em": hoje.strftime("%d/%m/%Y %H:%M"),
        "responsavel": responsavel_relatorio,
        "orcamentos_analisados": len(orcamentos),
        "receita_aprovada": aprovados["valor"],
        "receita_aprovada_formatada": _moeda(aprovados["valor"]),
        "valor_negociacao": em_espera["valor"],
        "valor_negociacao_formatado": _moeda(em_espera["valor"]),
        "valor_perdido": declinados["valor"],
        "valor_perdido_formatado": _moeda(declinados["valor"]),
        "aprovados": aprovados["quantidade"],
        "declinados": declinados["quantidade"],
        "em_espera": em_espera["quantidade"],
        "decisoes": decisoes,
        "taxa_ganho": taxa_ganho,
        "ticket_medio": ticket_vendas,
        "ticket_medio_formatado": _moeda(ticket_vendas),
        "observacoes": observacoes_count,
    }

    return render_template(
        "relatorio_vendas.html",
        periodo_label=periodo_label,
        resumo=resumo_executivo,
        dashboard=dashboard,
        orcamentos=detalhe_dashboard["recentes"],
        status_resumo=status_resumo,
        formas_pagamento=formas_pagamento,
        vendedores=vendedores,
        tipos_cliente=tipos_cliente,
        clientes_resumo=clientes_resumo,
        mes=mes_filtro or "todos",
        ano=ano_filtro or "todos",
        usuarios=usuarios,
        vendedor_filtro=vendedor_filtro,
        status_filtro=status_filtro,
        moeda=_moeda,
    )

@app.route('/orcamentos', methods=['GET', 'POST'])
def listar_orcamentos():
    selected_cliente_id = None
    selected_material_id = None
    selected_ambiente_id = None
    selected_descricao_id = None
    selected_produto_id = None

    # Obter parâmetros de filtro da query string
    filtro_cliente = request.args.get('filtro_cliente', 'Todos')
    filtro_data_inicio = request.args.get('filtro_data_inicio', '')
    filtro_data_fim = request.args.get('filtro_data_fim', '')
    limite = request.args.get('limite', '15')
    
    # Converter limite para inteiro, tratando o caso 'all'
    try:
        if limite == '0' or limite.lower() == 'all':
            limite_int = 0  # 0 significa carregar todos
        else:
            limite_int = int(limite)
    except (ValueError, TypeError):
        limite_int = 15  # Valor padrão

    if request.method == 'POST':
        cliente_id = request.form.get('cliente_id')
        ambiente_id = request.form.get('ambiente_id')
        produto_id = request.form.get('produto_id')  # NOVO CAMPO
        tipo_produto = request.form['tipo_produto']
        descricao_id = request.form.get('descricao_id')
        material_id = request.form['material_id']
        quantidade = int(request.form['quantidade'])
        comprimento = float(request.form.get('comprimento', 0) or 0)
        largura = float(request.form.get('largura', 0) or 0)
        instalacao = request.form.get('instalacao', 'Não')  # padrão = "Não"
        instalacao_valor = float(request.form.get('instalacao_valor', 0) or 0)
        rt = request.form.get('rt', 'Não')
        rt_percentual = float(request.form.get('rt_percentual', 0) or 0)
        if rt == 'Sim' and rt_percentual <= 0:
            rt_percentual = float(empresa_config_dict().get('rt_percentual_padrao') or 10)
        data_atual = datetime.now(br_tz)
        dono = session['user_cpf']

        # Campos dinâmicos
        comprimento_saia = float(request.form.get('comprimento_saia', 0) or 0)
        largura_saia = float(request.form.get('largura_saia', 0) or 0)
        comprimento_fronte = float(request.form.get('comprimento_fronte', 0) or 0)
        largura_fronte = float(request.form.get('largura_fronte', 0) or 0)
        tipo_cuba = request.form.get('tipo_cuba', '')
        quantidade_cubas = int(request.form.get('quantidade_cubas', 0) or 0)
        comprimento_cuba = float(request.form.get('comprimento_cuba', 0) or 0)
        largura_cuba = float(request.form.get('largura_cuba', 0) or 0)
        profundidade_cuba = float(request.form.get('profundidade_cuba', 0) or 0)
        acessorios = normalizar_acessorios(
            request.form.getlist('acessorio_nome[]'),
            request.form.getlist('acessorio_valor[]'),
        )
        tem_cooktop = 'Sim' if any(item.get('nome') == 'Cooktop' for item in acessorios) else request.form.get('tem_cooktop', 'Não')
        profundidade_nicho = float(request.form.get('profundidade_nicho', 0) or 0)
        tem_fundo = request.form.get('tem_fundo', 'Não')
        tem_alisar = request.form.get('tem_alisar', 'Não')
        largura_alisar = float(request.form.get('largura_alisar', 0) or 0)
        data=data_atual

        

        tipo_cuba = request.form.get('tipo_cuba', '')
        quantidade_cubas = int(request.form.get('quantidade_cubas', 0)) if tipo_cuba else 0

        tem_cooktop = 'Sim' if any(item.get('nome') == 'Cooktop' for item in acessorios) else request.form.get('tem_cooktop', 'Não')

        material = Material.query.get(material_id)

        modelo_cuba = request.form.get("modelo_cuba", "").strip()
        if not modelo_cuba:  
            modelo_cuba = "Normal"

        valor_total = calcular_valor_item(
            tipo_produto=tipo_produto,
            valor_material=material.valor,
            quantidade=quantidade,
            comprimento=comprimento,
            largura=largura,
            instalacao=instalacao,
            instalacao_valor=instalacao_valor,
            rt=rt,
            rt_percentual=rt_percentual,
            comprimento_saia=comprimento_saia,
            largura_saia=largura_saia,
            comprimento_fronte=comprimento_fronte,
            largura_fronte=largura_fronte,
            tipo_cuba=tipo_cuba,
            quantidade_cubas=quantidade_cubas,
            comprimento_cuba=comprimento_cuba,
            largura_cuba=largura_cuba,
            profundidade_cuba=profundidade_cuba,
            modelo_cuba=modelo_cuba,
            tem_cooktop=tem_cooktop,
            acessorios_valor_total=acessorios_total(acessorios),
            profundidade_nicho=profundidade_nicho,
            tem_fundo=tem_fundo,
            tem_alisar=tem_alisar,
            largura_alisar=largura_alisar,
            **opcoes_precificacao_empresa(),
        )

        if cliente_id and material_id and ambiente_id:
            novo_orcamento = Orcamento(
                cliente_id=cliente_id,
                ambiente_id=ambiente_id,
                descricao_id=descricao_id,
                produto_id=produto_id,
                tipo_produto=tipo_produto,
                material_id=material_id,
                quantidade=quantidade,
                comprimento=comprimento,
                largura=largura,
                instalacao=instalacao,
                instalacao_valor=instalacao_valor,
                rt=rt,
                rt_percentual=rt_percentual,
                comprimento_saia=comprimento_saia,
                largura_saia=largura_saia,
                comprimento_fronte=comprimento_fronte,
                largura_fronte=largura_fronte,
                tipo_cuba=tipo_cuba,
                quantidade_cubas=quantidade_cubas,
                comprimento_cuba=comprimento_cuba,
                largura_cuba=largura_cuba,
                profundidade_cuba=profundidade_cuba,
                tem_cooktop=tem_cooktop,
                acessorios_json=json.dumps(acessorios, ensure_ascii=False),
                profundidade_nicho=profundidade_nicho,
                tem_fundo=tem_fundo,
                tem_alisar=tem_alisar,
                largura_alisar=largura_alisar,
                valor_total=valor_total,
                modelo_cuba=modelo_cuba,
                dono=session['user_cpf']
            )
            db.session.add(novo_orcamento)
            db.session.commit()

            selected_cliente_id = int(cliente_id)
            selected_material_id = int(material_id)
            selected_ambiente_id = int(ambiente_id)
            selected_descricao_id = int(descricao_id) if descricao_id else None

        return redirect(url_for('listar_orcamentos'))

    user_cpf = session.get('user_cpf')

    if not user_cpf:
        flash("Faça login para acessar os orçamentos.", "error")
        return redirect(url_for('login'))

    # Construir query base
    if session.get('admin'):
        query = db.session.query(
            Orcamento,
            Usuario.nome.label('nome_usuario')
        ).join(Usuario, Orcamento.dono == Usuario.cpf)
    else:
        query = db.session.query(
            Orcamento,
            Usuario.nome.label('nome_usuario')
        ).join(Usuario, Orcamento.dono == Usuario.cpf).filter(Orcamento.dono == user_cpf)

    # Aplicar filtros
    if filtro_cliente != 'Todos':
        query = query.join(Cliente).filter(Cliente.nome == filtro_cliente)
    
    if filtro_data_inicio:
        try:
            data_inicio = datetime.strptime(filtro_data_inicio, '%Y-%m-%d')
            query = query.filter(Orcamento.data >= data_inicio)
        except ValueError:
            pass
    
    if filtro_data_fim:
        try:
            data_fim = datetime.strptime(filtro_data_fim, '%Y-%m-%d')
            # Adicionar 1 dia para incluir o dia final
            data_fim = data_fim.replace(hour=23, minute=59, second=59)
            query = query.filter(Orcamento.data <= data_fim)
        except ValueError:
            pass

    # Ordenar e limitar
    query = query.order_by(Orcamento.data.desc())
    
    if limite_int > 0:  # Aplicar limite apenas se for maior que 0
        query = query.limit(limite_int)

    orcamentos = query.all()

    # Carregar listas para os selects
    if session.get('admin'):
        clientes = Cliente.query.order_by(Cliente.nome).all()
        ambientes = Ambiente.query.order_by(Ambiente.nome).all()
        descricoes = Descricao.query.order_by(Descricao.nome).all()
        produtos = Produto.query.order_by(Produto.nome).all()  # NOVO
    else:
        clientes = Cliente.query.filter_by(dono=user_cpf).order_by(Cliente.nome).all()
        ambientes = Ambiente.query.filter_by(dono=user_cpf).order_by(Ambiente.nome).all()
        descricoes = Descricao.query.filter_by(dono=user_cpf).order_by(Descricao.nome).all()
        produtos = Produto.query.filter_by(dono=user_cpf).order_by(Produto.nome).all()  # NOVO

    materiais = Material.query.order_by(Material.nome).all()
    is_admin = session.get('admin', False)

    return render_template(
        'orcamentos.html',
        orcamentos=orcamentos,
        clientes=clientes,
        ambientes=ambientes,
        descricoes=descricoes,
        produtos=produtos,
        materiais=materiais,
        is_admin=is_admin,
        # Passar os filtros atuais para o template
        filtro_cliente_atual=filtro_cliente,
        filtro_data_inicio_atual=filtro_data_inicio,
        filtro_data_fim_atual=filtro_data_fim,
        limite_atual=limite_int,
        cuba_valores=empresa_cuba_valores(),
        acessorio_valores=empresa_acessorios_valores(),
    )

    
import re  # Para usar expressões regulares


    
@app.route('/clientes', methods=['GET', 'POST'])
def clientes():
    if 'user_cpf' not in session:  # Se não estiver logado, redireciona para login
        return redirect(url_for('login'))

    if request.method == 'POST':
        nome = request.form['nome']
        endereco = request.form.get('endereco', '')
        telefone = request.form.get('telefone', '')
        pais_selecionado = request.form.get('pais_selecionado', 'BR')
        codigo_pais = request.form.get('codigo_pais', '55')
        dono = session['user_cpf']  # Define o dono como o CPF do usuário logado

        # APENAS adicionar código do país se não for Brasil
        # O JAVASCRIPT já cuidou da formatação - NÃO CHAMAR formatar_telefone
        if pais_selecionado != 'BR' and not telefone.startswith('+'):
            telefone = f"+{codigo_pais} {telefone}"
        # Para Brasil, manter exatamente como o JavaScript formatou
        # NÃO FAZER NADA - telefone já está formatado pelo frontend

        # Verifica se o cliente já existe pelo telefone e dono
        cliente_existente = Cliente.query.filter_by(telefone=telefone, dono=dono).first()
        if cliente_existente:
            flash("Esse cliente já está cadastrado!", "error_clientes")
            return redirect(url_for('clientes'))
        
        # Criar novo cliente (agora com dono)
        novo_cliente = Cliente(
            nome=nome,
            endereco=endereco,
            telefone=telefone,
            dono=dono
        )
        
        db.session.add(novo_cliente)
        db.session.commit()
        
        flash("Cliente cadastrado com sucesso!", "success_clientes")
        return redirect(url_for('clientes'))

    # Verifica se o usuário logado é administrador
    is_admin = session.get('admin', False)

    if is_admin:
        # Admin vê todos os clientes - ORDENADO POR NOME (case-insensitive no Python)
        clientes_query = db.session.query(Cliente, Usuario.nome.label('nome_usuario'))\
                                  .join(Usuario, Cliente.dono == Usuario.cpf)\
                                  .all()
    else:
        # Usuário comum vê apenas os clientes que ele cadastrou - ORDENADO POR NOME
        clientes_query = db.session.query(Cliente, Usuario.nome.label('nome_usuario'))\
                                  .join(Usuario, Cliente.dono == Usuario.cpf)\
                                  .filter(Cliente.dono == session['user_cpf'])\
                                  .all()

    # Ordenar os resultados por nome (case-insensitive no Python)
    clientes = sorted(clientes_query, key=lambda x: x.Cliente.nome.lower())

    return render_template('clientes.html', clientes=clientes)




@app.route('/materiais', methods=['GET', 'POST'])
def materiais():
    if request.method == 'POST':
        nome = request.form['nome']
        valor = float(request.form['valor'])

        novo_material = Material(nome=nome, valor=valor)
        db.session.add(novo_material)
        db.session.commit()
        return redirect(url_for('materiais'))

    materiais = Material.query.order_by(db.func.lower(Material.nome)).all()
    return render_template('materiais.html', materiais=materiais)


@app.route('/configuracoes', methods=['GET', 'POST'])
def configuracoes():
    if not session.get('admin'):
        flash("Acesso restrito a administradores.", "error")
        return redirect(url_for('index'))

    config = obter_config_empresa()
    if not config:
        flash("Não foi possível carregar as configurações da empresa.", "error")
        return redirect(url_for('index'))

    if request.method == 'POST':
        config.nome_empresa = request.form.get('nome_empresa', config.nome_empresa).strip() or config.nome_empresa
        config.razao_social = request.form.get('razao_social', '').strip()
        config.documento = request.form.get('documento', '').strip()
        config.telefone = request.form.get('telefone', '').strip()
        config.endereco = request.form.get('endereco', '').strip()
        config.cor_primaria = request.form.get('cor_primaria', '#4e73df').strip() or '#4e73df'
        config.prazo_entrega_padrao = int(float(request.form.get('prazo_entrega_padrao', 15) or 15))
        config.desconto_avista_padrao = float(request.form.get('desconto_avista_padrao', 5) or 5)
        config.desconto_parcelado_padrao = float(request.form.get('desconto_parcelado_padrao', 10) or 10)
        config.observacoes_padrao = request.form.get('observacoes_padrao', '').strip() or _config_empresa_fallback()['observacoes_padrao']
        config.max_parcelas_padrao = int(request.form.get('max_parcelas_padrao', 10) or 10)
        config.valor_minimo_parcela = float(request.form.get('valor_minimo_parcela', 100) or 100)
        for chave, padrao in PAGAMENTOS_PADRAO.items():
            setattr(config, f'pagamento_{chave}_ativo', request.form.get(f'pagamento_{chave}_ativo') == 'on')
            setattr(config, f'pagamento_{chave}_titulo', request.form.get(f'pagamento_{chave}_titulo', '').strip() or padrao['titulo'])
            setattr(config, f'pagamento_{chave}_descricao', request.form.get(f'pagamento_{chave}_descricao', '').strip() or padrao['descricao'])
        config.cooktop_valor = float(request.form.get('cooktop_valor', 50) or 50)
        config.nicho_mao_obra = float(request.form.get('nicho_mao_obra', 150) or 150)
        config.nicho_sem_fundo_mao_obra = float(request.form.get('nicho_sem_fundo_mao_obra', 150) or 150)
        config.rt_percentual_padrao = float(request.form.get('rt_percentual_padrao', 10) or 10)
        config.minimo_medida_cm = float(request.form.get('minimo_medida_cm', 10) or 10)
        config.pedra_simples_margem = float(request.form.get('pedra_simples_margem', 0) or 0)
        config.soleira_margem = float(request.form.get('soleira_margem', 0) or 0)
        config.ilharga_margem = float(request.form.get('ilharga_margem', 0) or 0)
        config.pedra_simples_com_saia_margem = float(request.form.get('pedra_simples_com_saia_margem', 0) or 0)
        config.bancada_margem_ate_1000 = float(request.form.get('bancada_margem_ate_1000', 30) or 30)
        config.bancada_margem_ate_2000 = float(request.form.get('bancada_margem_ate_2000', 15) or 15)
        config.bancada_margem_acima_2000 = float(request.form.get('bancada_margem_acima_2000', 10) or 10)
        config.ilharga_bipolida_margem = float(request.form.get('ilharga_bipolida_margem', 15) or 15)
        config.pedra_bipolida_com_saia_margem = float(request.form.get('pedra_bipolida_com_saia_margem', 15) or 15)
        config.pedra_bipolida_margem = float(request.form.get('pedra_bipolida_margem', 15) or 15)
        config.pedra_box_adicional = float(request.form.get('pedra_box_adicional', 30) or 30)
        config.nicho_folga_cm = float(request.form.get('nicho_folga_cm', 4) or 4)
        config.saia_margem = float(request.form.get('saia_margem', 0) or 0)
        config.fronte_margem = float(request.form.get('fronte_margem', 0) or 0)
        config.alisar_margem = float(request.form.get('alisar_margem', 0) or 0)

        cuba_valores = {}
        cuba_nomes = request.form.getlist('cuba_nome[]')
        cuba_precos = request.form.getlist('cuba_valor[]')
        for nome_cuba, valor_cuba in zip(cuba_nomes, cuba_precos):
            nome_limpo = (nome_cuba or '').strip()
            if nome_limpo:
                cuba_valores[nome_limpo] = float(valor_cuba or 0)
        if not cuba_valores:
            cuba_valores = dict(CUBA_VALORES_PADRAO)
        config.cuba_valores_json = json.dumps(cuba_valores, ensure_ascii=False)

        acessorio_valores = {}
        acessorio_nomes = request.form.getlist('acessorio_nome[]')
        acessorio_precos = request.form.getlist('acessorio_valor[]')
        for nome_acessorio, valor_acessorio in zip(acessorio_nomes, acessorio_precos):
            nome_limpo = (nome_acessorio or '').strip()
            if nome_limpo:
                acessorio_valores[nome_limpo] = float(valor_acessorio or 0)
        if not acessorio_valores:
            acessorio_valores = dict(ACESSORIOS_VALORES_PADRAO)
        config.acessorios_valores_json = json.dumps(acessorio_valores, ensure_ascii=False)
        config.cooktop_valor = float(acessorio_valores.get("Cooktop", config.cooktop_valor or 50) or 0)

        config.vendas_tipos_cliente_json = json.dumps(
            _normalizar_lista_texto(
                request.form.getlist('vendas_tipo_cliente[]'),
                CATEGORIAS_VENDAS_PADRAO["tipos_cliente"],
            ),
            ensure_ascii=False,
        )
        config.vendas_formas_pagamento_json = json.dumps(
            _normalizar_lista_texto(
                request.form.getlist('vendas_forma_pagamento[]'),
                CATEGORIAS_VENDAS_PADRAO["formas_pagamento"],
            ),
            ensure_ascii=False,
        )

        logo = request.files.get('logo')
        if logo and logo.filename and _logo_permitida(logo.filename):
            ext = secure_filename(logo.filename).rsplit('.', 1)[1].lower()
            filename = f"empresa_logo.{ext}"
            logo_bytes = logo.read()
            config.logo_data = base64.b64encode(logo_bytes).decode("ascii")
            config.logo_mime = logo.mimetype or _mime_logo_por_extensao(filename)
            config.logo_filename = filename

        db.session.commit()
        flash("Configurações salvas com sucesso.", "config_success")
        return redirect(url_for('configuracoes'))

    return render_template(
        'configuracoes.html',
        config=config,
        cuba_valores=empresa_cuba_valores(config),
        cuba_padrao=CUBA_VALORES_PADRAO,
        acessorio_valores=empresa_acessorios_valores(config),
        acessorio_padrao=ACESSORIOS_VALORES_PADRAO,
        vendas_tipos_cliente=empresa_tipos_cliente(config),
        vendas_formas_pagamento=empresa_formas_pagamento_vendas(config),
        logo_url=empresa_logo_url(config),
    )

@app.route('/clientes/edit/<int:id>', methods=['GET', 'POST'])
def editar_cliente(id):
    cliente = Cliente.query.get_or_404(id)

    if request.method == 'POST':
        nome = request.form['nome']
        endereco = request.form['endereco']
        telefone = request.form.get('telefone', '')
        pais_selecionado = request.form.get('pais_selecionado', 'BR')
        codigo_pais = request.form.get('codigo_pais', '55')

        # APENAS adicionar código do país se não for Brasil
        # O JAVASCRIPT já cuidou da formatação - NÃO CHAMAR formatar_telefone
        if pais_selecionado != 'BR' and not telefone.startswith('+'):
            telefone = f"+{codigo_pais} {telefone}"
        # Para Brasil, manter exatamente como está

        # Atualiza os dados
        cliente.nome = nome
        cliente.endereco = endereco
        cliente.telefone = telefone
        db.session.commit()

        flash("Cliente atualizado com sucesso!", "success")
        return redirect(url_for('clientes'))

    return redirect(url_for('clientes'))


@app.route('/materiais/edit/<int:id>', methods=['GET', 'POST'])
def editar_material(id):
    material = Material.query.get_or_404(id)
    if request.method == 'POST':
        material.nome = request.form['nome']
        material.valor = float(request.form['valor'])
        db.session.commit()
        return redirect(url_for('materiais'))
    return redirect(url_for('materiais'))

@app.route('/orcamentos/edit/<int:id>', methods=['GET', 'POST'])
def editar_orcamento(id):
    orcamento = Orcamento.query.get_or_404(id)
    if not orcamento:
        flash("Erro: Orçamento não encontrado!", "error")
        return redirect(url_for('listar_orcamentos'))

    # Obtendo CPF do usuário logado
    usuario_cpf = session.get('user_cpf')  
    usuario = Usuario.query.filter_by(cpf=usuario_cpf).first()

    # Filtrar apenas os clientes cujo dono é o usuário logado
    clientes = Cliente.query.filter_by(dono=usuario_cpf).all()
    ambientes = Ambiente.query.filter_by(dono=usuario_cpf).order_by(Ambiente.nome).all()
    materiais = Material.query.all()
    descricoes = Descricao.query.filter_by(dono=usuario_cpf).order_by(Descricao.nome).all()
    produtos = Produto.query.filter_by(dono=usuario_cpf).order_by(Produto.nome).all()

    # 🔥 CORREÇÃO DEFINITIVA: Filtrar orçamentos salvos
    if session.get('admin'):
        # Admin vê todos os orçamentos salvos
        orcamentos_salvos = OrcamentoSalvo.query.order_by(OrcamentoSalvo.codigo.desc()).all()
    else:
        # Usuário comum vê apenas os orçamentos salvos onde ele é o criador
        # Primeiro, vamos obter o nome do usuário logado
        nome_usuario_logado = usuario.nome if usuario else ""
        
        # Filtrar por criado_por (que armazena o nome do usuário)
        orcamentos_salvos = OrcamentoSalvo.query.filter_by(criado_por=nome_usuario_logado).order_by(OrcamentoSalvo.codigo.desc()).all()

        # 🔥 ALTERNATIVA: Se ainda estiver mostrando de outros usuários, use esta query mais restritiva
        if not orcamentos_salvos:
            orcamentos_salvos = []

    if request.method == 'POST':
        # Atualizando os dados do orçamento com as informações do formulário
        orcamento.cliente_id = request.form.get('cliente_id')
        orcamento.tipo_produto = request.form['tipo_produto']
        orcamento.ambiente_id = request.form.get('ambiente_id')
        orcamento.descricao_id = request.form.get('descricao_id')
        orcamento.produto_id = request.form.get('produto_id')  # NOVO CAMPO
        orcamento.material_id = request.form['material_id']
        orcamento.quantidade = int(request.form.get('quantidade', orcamento.quantidade))
        orcamento.comprimento = float(request.form.get('comprimento', orcamento.comprimento or 0)or 0)
        orcamento.largura = float(request.form.get('largura', orcamento.largura or 0)or 0)
        orcamento.instalacao = request.form.get('instalacao', orcamento.instalacao or 'Não')
        orcamento.instalacao_valor = float(request.form.get('instalacao_valor', orcamento.instalacao_valor or 0) or 0)
        orcamento.rt = request.form.get('rt', orcamento.rt)
        orcamento.rt_percentual = float(request.form.get('rt_percentual', orcamento.rt_percentual or 0)or 0)

        # Campos dinâmicos
        orcamento.comprimento_saia = float(request.form.get('comprimento_saia', orcamento.comprimento_saia or 0) or 0)
        orcamento.largura_saia = float(request.form.get('largura_saia', orcamento.largura_saia or 0) or 0)
        orcamento.comprimento_fronte = float(request.form.get('comprimento_fronte', orcamento.comprimento_fronte or 0) or 0)
        orcamento.largura_fronte = float(request.form.get('largura_fronte', orcamento.largura_fronte or 0) or 0)
        orcamento.tipo_cuba = request.form.get('tipo_cuba', orcamento.tipo_cuba)
        orcamento.quantidade_cubas = int(request.form.get('quantidade_cubas', orcamento.quantidade_cubas or 0) or 0)
        orcamento.comprimento_cuba = float(request.form.get('comprimento_cuba', orcamento.comprimento_cuba or 0) or 0)
        orcamento.largura_cuba = float(request.form.get('largura_cuba', orcamento.largura_cuba or 0) or 0)
        orcamento.profundidade_cuba = float(request.form.get('profundidade_cuba', orcamento.profundidade_cuba or 0) or 0)
        acessorios = normalizar_acessorios(
            request.form.getlist('acessorio_nome[]'),
            request.form.getlist('acessorio_valor[]'),
        )
        orcamento.tem_cooktop = 'Sim' if any(item.get('nome') == 'Cooktop' for item in acessorios) else request.form.get('tem_cooktop', orcamento.tem_cooktop)
        orcamento.acessorios_json = json.dumps(acessorios, ensure_ascii=False)
        orcamento.profundidade_nicho = float(request.form.get('profundidade_nicho', orcamento.profundidade_nicho or 0) or 0)
        orcamento.tem_fundo = request.form.get('tem_fundo', orcamento.tem_fundo)
        orcamento.tem_alisar = request.form.get('tem_alisar', orcamento.tem_alisar)
        orcamento.largura_alisar = float(request.form.get('largura_alisar', orcamento.largura_alisar or 0) or 0)
        orcamento.modelo_cuba = request.form.get('modelo_cuba', 'Normal')

        # Obtendo o material
        material = Material.query.get(orcamento.material_id)
        orcamento.valor_total = 0
        valor_total_criar = 0

        orcamento.comprimento_cal = max(orcamento.comprimento, 10)  # Garante mínimo de 10 cm
        orcamento.largura_cal = max(orcamento.largura, 10)  # Garante mínimo de 10 cm   
        # Cálculo do valor base do material
        valor_base = material.valor * (orcamento.comprimento_cal * orcamento.largura_cal / 10000)

        # Ajuste de preço para Bancada e Lavatorio
        if orcamento.tipo_produto in ['Bancada', 'Lavatorio']:
            if material.valor < 1000:
                valor_base *= 1.3
            elif material.valor < 2000:
                valor_base *= 1.15
            elif material.valor < 1000000:
                valor_base *= 1.1

        # Ajuste de preço para Ilharga Bipolida
        if orcamento.tipo_produto in ['Ilharga Bipolida', 'Pedra Bipolida com Saia', 'Pedra Bipolida'] and valor_base < 1000000:
            pricing_opts = opcoes_precificacao_empresa()
            margem_bipolida = pricing_opts.get('ilharga_bipolida_margem', 15)
            if orcamento.tipo_produto == 'Pedra Bipolida com Saia':
                margem_bipolida = pricing_opts.get('pedra_bipolida_com_saia_margem', 15)
            elif orcamento.tipo_produto == 'Pedra Bipolida':
                margem_bipolida = pricing_opts.get('pedra_bipolida_margem', 15)
            valor_base *= 1 + (float(margem_bipolida or 0) / 100)

        valor_total_criar += valor_base  # Inicializando o valor total

        # **Cálculo do Nicho**
        if orcamento.tipo_produto == 'Nicho':
            orcamento.comprimento_cal = 10 if 0 < orcamento.comprimento < 10 else orcamento.comprimento
            orcamento.largura_cal = 10 if 0 < orcamento.largura < 10 else orcamento.largura
            orcamento.profundidade_nicho_cal = 10 if 0 < orcamento.profundidade_nicho < 10 else orcamento.profundidade_nicho
            if orcamento.tem_fundo == 'Sim':  # Verifica se o nicho tem fundo
                area_nicho = ((orcamento.comprimento_cal + 4) * (orcamento.largura_cal + 4)) + \
                             (((orcamento.comprimento_cal + 4) * orcamento.profundidade_nicho_cal) * 2) + \
                             (((orcamento.largura_cal + 4) * orcamento.profundidade_nicho_cal) * 2)
            else:  # Caso o nicho não tenha fundo
                area_nicho = ((orcamento.comprimento_cal + 4) + (orcamento.largura_cal + 4)) * orcamento.profundidade_nicho_cal * 2

            # Verifica se há alisar e ajusta a área do nicho
            if orcamento.tem_alisar == 'Sim' and orcamento.largura_alisar > 0:
                orcamento.largura_alisar_cal = 10 if 0 < orcamento.largura_alisar < 10 else orcamento.largura_alisar
                area_nicho += ((orcamento.comprimento_cal + (orcamento.largura_alisar_cal * 2)) * orcamento.largura_alisar_cal * 2) + \
                              ((orcamento.largura_cal + (orcamento.largura_alisar_cal * 2)) * orcamento.largura_alisar_cal * 2)

            # Calcula o valor do nicho e adiciona ao total
            valor_nicho = (area_nicho / 10000) * material.valor + 150
            valor_total_criar = valor_nicho
                                       
        # **Cálculo do Acabamento Saia**
        if orcamento.tipo_produto in ['Ilharga', 'Ilharga Bipolida', 'Pedra Simples com Saia', 'Pedra Bipolida com Saia', 'Bancada', 'Lavatorio']:
            orcamento.comprimento_saia_cal = 10 if 0 < orcamento.comprimento_saia < 10 else orcamento.comprimento_saia
            orcamento.largura_saia_cal = 10 if 0 < orcamento.largura_saia < 10 else orcamento.largura_saia
            valor_saia = orcamento.comprimento_saia_cal * orcamento.largura_saia_cal * material.valor / 10000
            valor_total_criar += valor_saia

        # **Cálculo do Acabamento Fronte**
        if orcamento.tipo_produto in ['Bancada', 'Lavatorio']:
            orcamento.comprimento_fronte_cal = 10 if 0 < orcamento.comprimento_fronte < 10 else orcamento.comprimento_fronte
            orcamento.largura_fronte_cal = 10 if 0 < orcamento.largura_fronte < 10 else orcamento.largura_fronte
            valor_fronte = orcamento.comprimento_fronte_cal * orcamento.largura_fronte_cal * material.valor / 10000
            valor_total_criar += valor_fronte

        # **Cálculo da Pedra de Box**
        if orcamento.tipo_produto == 'Pedra de Box':
            pricing_opts = opcoes_precificacao_empresa()
            valor_total_criar = (valor_base * 2) + ((orcamento.comprimento or 0) / 100) * pricing_opts.get('pedra_box_adicional', 30)

        # **Adicionando o valor das cubas**
        cuba_valores = {
            'Embutida': 225,
            'Esculpida': 175,
            'Tradicional Inox': 225,
            'Tanque Inox': 500,
            'Apoio Cliente': 125,
            'Embutida Cliente': 125,
            'Gourmet Cliente': 225,
            'Sobrepor Cliente': 125,
            'Tanque Inox Cliente': 225
        }
        
        # **Adicionando o valor das cubas**
        if orcamento.tipo_cuba:
            valor_cuba = cuba_valores.get(orcamento.tipo_cuba, 0)
            valor_total_criar += valor_cuba * orcamento.quantidade_cubas

            if orcamento.tipo_cuba == 'Esculpida':
                modelo_cuba = request.form.get('modelo_cuba', 'Normal')
                comprimento_cuba = float(request.form.get('orcamento.comprimento_cuba', 0))
                largura_cuba = float(request.form.get('orcamento.largura_cuba', 0))
                profundidade_cuba = float(request.form.get('orcamento.profundidade_cuba', 0))
            
                if modelo_cuba == 'Prainha':
                    m2_cuba = ((orcamento.comprimento_cuba * orcamento.largura_cuba) + (orcamento.largura_cuba * 2) * orcamento.profundidade_cuba) / 10000
                else:
                    m2_cuba = ((orcamento.comprimento_cuba * orcamento.largura_cuba * 2) +
                               (orcamento.comprimento_cuba * 2 + orcamento.largura_cuba * 2) * orcamento.profundidade_cuba) / 10000
            
                valor_cuba_esculpida = m2_cuba * material.valor * orcamento.quantidade_cubas
                valor_total_criar += valor_cuba_esculpida

        # **Definindo o valor fixo do cooktop**
        cooktop_valor = 50  # Valor fixo para o cooktop

        # **Adicionando o valor do cooktop**
        if orcamento.tem_cooktop == 'Sim':
            valor_total_criar += cooktop_valor
        else:
            orcamento.tem_cooktop = 'Não'  # Define explicitamente como "Não" se não for "Sim"
        print(f"Valor do campo tem_cooktop: {orcamento.tem_cooktop}")

        if orcamento.instalacao == 'Sim':
            valor_total_criar += orcamento.instalacao_valor

        valor_total_criar *= orcamento.quantidade

        valor_rt = 0.0
        # **Aplicando RT**
        if orcamento.rt == 'Sim' and orcamento.rt_percentual > 0:
            valor_rt = valor_total_criar / (1 - orcamento.rt_percentual / 100) - valor_total_criar

        # Arredonda apenas o valor final
        orcamento.valor_total = calcular_valor_item(
            tipo_produto=orcamento.tipo_produto,
            valor_material=material.valor,
            quantidade=orcamento.quantidade,
            comprimento=orcamento.comprimento,
            largura=orcamento.largura,
            instalacao=orcamento.instalacao,
            instalacao_valor=orcamento.instalacao_valor,
            rt=orcamento.rt,
            rt_percentual=orcamento.rt_percentual,
            comprimento_saia=orcamento.comprimento_saia,
            largura_saia=orcamento.largura_saia,
            comprimento_fronte=orcamento.comprimento_fronte,
            largura_fronte=orcamento.largura_fronte,
            tipo_cuba=orcamento.tipo_cuba,
            quantidade_cubas=orcamento.quantidade_cubas,
            comprimento_cuba=orcamento.comprimento_cuba,
            largura_cuba=orcamento.largura_cuba,
            profundidade_cuba=orcamento.profundidade_cuba,
            modelo_cuba=orcamento.modelo_cuba,
            tem_cooktop=orcamento.tem_cooktop,
            acessorios_valor_total=acessorios_total(acessorios_do_orcamento(orcamento)),
            profundidade_nicho=orcamento.profundidade_nicho,
            tem_fundo=orcamento.tem_fundo,
            tem_alisar=orcamento.tem_alisar,
            largura_alisar=orcamento.largura_alisar,
            **opcoes_precificacao_empresa(),
        )
        
        orcamento_salvo = OrcamentoSalvo.query.filter(OrcamentoSalvo.orcamentos_ids.contains(str(orcamento.id))).first()
        if orcamento_salvo:
            atualizar_valor_orcamento_salvo(orcamento_salvo.id)
            
        orcamento_salvo_id = request.form.get('orcamento_salvo_id')

        # Se for None ou string vazia, mantém como None
        if not orcamento_salvo_id or orcamento_salvo_id.strip() == "":
            orcamento_salvo_id = None
        else:
            try:
                orcamento_salvo_id = int(orcamento_salvo_id)
            except ValueError:
                orcamento_salvo_id = None  # Se der erro, mantém como None para evitar crash        

        if orcamento_salvo_id:
            orcamento_salvo_novo = OrcamentoSalvo.query.get(orcamento_salvo_id)

            if orcamento_salvo_novo:
                ids_atualizados = orcamento_salvo_novo.orcamentos_ids.split(',') if orcamento_salvo_novo.orcamentos_ids else []
                if str(orcamento.id) not in ids_atualizados:
                    ids_atualizados.append(str(orcamento.id))
                    orcamento_salvo_novo.orcamentos_ids = ','.join(ids_atualizados)

                    # **Somente atualiza se o orçamento salvo existir**
                    if orcamento_salvo_novo.id:
                        atualizar_valor_orcamento_salvo(orcamento_salvo_novo.id)
                        flash("Orçamento vinculado com sucesso!", "success")
        
        db.session.commit()
        return redirect(url_for('listar_orcamentos'))

    return render_template(
        'editar_orcamento.html',
        orcamento=orcamento,
        ambientes=ambientes,
        descricoes=descricoes,
        produtos=produtos,
        clientes=clientes,
        materiais=materiais,
        orcamentos_salvos=orcamentos_salvos,
        cuba_valores=empresa_cuba_valores(),
        acessorio_valores=empresa_acessorios_valores(),
        acessorios_orcamento=acessorios_do_orcamento(orcamento),
    )

@app.route('/clientes/delete/<int:id>', methods=['POST'])
def deletar_cliente(id):
    cliente = Cliente.query.get(id)
    if cliente:
        try:
            db.session.delete(cliente)
            db.session.commit()
            return jsonify({"success": "Cliente deletado com sucesso!"})
        except Exception as e:
            db.session.rollback()
            return jsonify({"error": f"Erro ao excluir cliente: {str(e)}"}), 500
    return jsonify({"error": "Cliente não encontrado!"}), 404


@app.route('/materiais/delete/<int:id>', methods=['POST'])
def deletar_material(id):
    material = Material.query.get(id)
    if material:
        db.session.delete(material)
        db.session.commit()
    return redirect(url_for('materiais'))

@app.route('/deletar_orcamento/<int:id>', methods=['POST'])
def deletar_orcamento(id):
    """Esta rota exclui fisicamente do banco de dados (apenas do gerenciador)"""
    orcamento = Orcamento.query.get(id)
    if not orcamento:
        flash("Erro: Orçamento não encontrado.", "error")
        return redirect(url_for('listar_orcamentos'))

    # Verifica se esse orçamento pertence a um orçamento salvo
    orcamento_salvo = OrcamentoSalvo.query.filter(
        OrcamentoSalvo.orcamentos_ids.like(f'%{id}%')
    ).first()

    # 🔥 AGORA: Se estiver em um orçamento salvo, apenas remove da lista
    if orcamento_salvo:
        # Remover da lista de IDs
        ids = orcamento_salvo.orcamentos_ids.split(',')
        ids_atualizados = [item_id for item_id in ids if item_id.strip() != str(id)]
        
        # Se ainda houver itens, atualizar
        if ids_atualizados:
            orcamento_salvo.orcamentos_ids = ','.join(ids_atualizados)
            
            # Recalcular valor
            orcamentos_restantes = Orcamento.query.filter(
                Orcamento.id.in_([int(item_id) for item_id in ids_atualizados if item_id.strip().isdigit()])
            ).all()
            
            orcamento_salvo.valor_total = sum(orc.valor_total for orc in orcamentos_restantes)
            
            flash(f"Item removido do orçamento salvo {orcamento_salvo.codigo}.", "warning")
        else:
            # Se não houver mais itens, excluir o orçamento salvo
            db.session.delete(orcamento_salvo)
            flash(f"Orçamento salvo {orcamento_salvo.codigo} excluído por não ter mais itens.", "warning")

    # ðŸ”¥ EXCLUIR FISICAMENTE (apenas da tabela Orcamento)
    db.session.delete(orcamento)
    db.session.commit()

    flash("Orçamento excluído com sucesso!", "success")
    return redirect(url_for('listar_orcamentos'))


# 🚀 Rota para deletar **múltiplos orçamentos selecionados**
@app.route('/orcamentos/delete_selecionados', methods=['POST'])
def deletar_orcamentos_selecionados():
    try:
        # Obtém os IDs enviados via AJAX
        ids = request.json.get('ids', [])

        if not ids:
            return jsonify({'error': 'Nenhum orçamento selecionado!'}), 400

        # Converte os IDs para inteiros
        ids = [int(id) for id in ids if id.isdigit()]

        if not ids:
            return jsonify({'error': 'IDs inválidos!'}), 400

        # Deleta os orçamentos no banco de dados
        Orcamento.query.filter(Orcamento.id.in_(ids)).delete(synchronize_session=False)
        db.session.commit()

        return jsonify({'success': 'Orçamentos deletados com sucesso!'})

    except Exception as e:
        return jsonify({'error': f'Erro ao deletar: {str(e)}'}), 500

@app.route('/detalhes_orcamento', methods=['GET'])
def detalhes_orcamento():
    try:
        # Obter os IDs dos orçamentos selecionados
        ids = request.args.get('ids', '')

        if not ids.strip():
            return "Nenhum orçamento selecionado!", 400

        # Converter os IDs em uma lista de inteiros
        ids = [int(id.strip()) for id in ids.split(",") if id.strip().isdigit()]

        if not ids:
            return "Nenhum orçamento válido selecionado!", 400

        # Buscar os orçamentos no banco de dados
        orcamentos = Orcamento.query.filter(Orcamento.id.in_(ids)).all()

        if not orcamentos:
            return "Nenhum orçamento encontrado!", 404

        # NOVO: Agrupar orçamentos por AMBIENTE -> DESCRIÇÃO -> TIPO DE PRODUTO
        ambientes_agrupados = {}
        for orcamento in orcamentos:
            ambiente_nome = orcamento.ambiente.nome if orcamento.ambiente else 'Sem Ambiente'
            
            if ambiente_nome not in ambientes_agrupados:
                ambientes_agrupados[ambiente_nome] = {}
            
            # DENTRO de cada ambiente, agrupar por DESCRIÇÃO
            descricao_nome = orcamento.descricao.nome if orcamento.descricao else 'Sem Descrição'
            
            if descricao_nome not in ambientes_agrupados[ambiente_nome]:
                ambientes_agrupados[ambiente_nome][descricao_nome] = {}
            
            # DENTRO de cada descrição, agrupar por TIPO DE PRODUTO
            tipo_produto = orcamento.tipo_produto
            if tipo_produto not in ambientes_agrupados[ambiente_nome][descricao_nome]:
                ambientes_agrupados[ambiente_nome][descricao_nome][tipo_produto] = []
            
            ambientes_agrupados[ambiente_nome][descricao_nome][tipo_produto].append(orcamento)

        # Obter o nome do cliente do primeiro orçamento
        cliente_nome = orcamentos[0].cliente.nome if orcamentos else "Orçamentos"

        valor_total_final = sum(o.valor_total for o in orcamentos)
        valor_total_formatado = "R$ {:,.2f}".format(valor_total_final).replace(",", "X").replace(".", ",").replace("X", ".")
        valor_total_float = valor_total_final

        # Obter informações do usuário logado
        usuario = Usuario.query.filter_by(cpf=session.get('user_cpf')).first()
        telefone_usuario = usuario.telefone if usuario else ""
        vendedor_nome = usuario.nome if usuario else ""

        return render_template(
            'detalhes_orcamento.html',
            orcamentos=orcamentos,
            ambientes_agrupados=ambientes_agrupados,  # NOVO: estrutura de agrupamento
            cliente_nome=cliente_nome,
            valor_total_final=valor_total_formatado,
            valor_total_float=valor_total_float,
            telefone_usuario=telefone_usuario,
            vendedor_nome=vendedor_nome,
            # Adicionar valores padrão para manter compatibilidade com o template
            prazo_entrega=15,
            desconto_avista=5,
            desconto_parcelado=10,
            observacoes="Medidas sujeitas a confirmação no local. Valores válidos por 7 dias.",
            exclude_payments=[]
        )

    except Exception as e:
        return f"Erro ao carregar detalhes dos orçamentos: {str(e)}", 500

@app.route('/setup', methods=['GET', 'POST'])
def setup():
    if Usuario.query.first():
        return redirect(url_for('login'))
    if request.method == 'POST':
        nome = request.form.get('nome', '').strip()
        cpf = request.form.get('cpf', '').strip()
        senha = request.form.get('senha', '').strip()
        if not nome or not cpf or not senha:
            flash("Preencha todos os campos!", "error")
            return render_template('setup.html')
        admin = Usuario(nome=nome, cpf=cpf, is_admin=True)
        admin.set_senha(senha)
        db.session.add(admin)
        db.session.commit()
        flash("Administrador criado com sucesso! Faça login.", "success")
        return redirect(url_for('login'))
    return render_template('setup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if not Usuario.query.first():
        return redirect(url_for('setup'))
    if request.method == 'POST':
        cpf = request.form['cpf'].strip()
        senha = request.form['senha']

        usuario = Usuario.query.filter_by(cpf=cpf).first()

        if not usuario:
            cpf_limpo = re.sub(r'[\.\-]', '', cpf)
            usuario = Usuario.query.filter_by(cpf=cpf_limpo).first()

        if not usuario and len(cpf) == 11 and cpf.isdigit():
            cpf_formatado = f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"
            usuario = Usuario.query.filter_by(cpf=cpf_formatado).first()

        if usuario:
            if not usuario.ativo:
                flash("Usuário desativado. Fale com o administrador.", "error")
                return render_template('login.html')

            if usuario.check_senha(senha):
                session['user_cpf'] = usuario.cpf
                session['admin'] = usuario.is_admin
                return redirect(url_for('index'))

        flash("Usuário ou senha incorretos!", "error")
        return render_template('login.html')

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user_cpf', None)
    session.pop('admin', None)
    return redirect(url_for('login'))

@app.route('/criar_usuario', methods=['GET', 'POST'])
def criar_usuario():
    if not session.get('admin'):  # Apenas o admin pode criar usuários
        return redirect(url_for('index'))

    if request.method == 'POST':
        nome = request.form.get('nome')
        cpf = request.form.get('cpf')
        telefone = request.form.get('telefone', '')  # Novo campo telefone
        senha = request.form.get('senha')

        if not nome or not cpf or not senha:
            flash("Todos os campos são obrigatórios!", "error")
            return redirect(url_for('criar_usuario'))

        try:
            novo_usuario = Usuario(nome=nome, cpf=cpf, telefone=telefone, is_admin=False, ativo=True)
            novo_usuario.set_senha(senha)

            db.session.add(novo_usuario)
            db.session.commit()

            flash("Usuário criado com sucesso!", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"Erro ao criar usuário: {str(e)}", "error")

        return redirect(url_for('gerenciar_usuarios'))

    return render_template('criar_usuario.html')




@app.route('/alterar_senha', methods=['GET', 'POST'])
def alterar_senha():
    if 'user_cpf' not in session:
        return redirect(url_for('login'))

    usuario = Usuario.query.filter_by(cpf=session['user_cpf']).first()

    if not usuario:
        flash("Erro: Usuário não encontrado!", "error")
        return redirect(url_for('index'))

    # ✅ Impede alteração da senha se for admin
    if usuario.is_admin:
        flash("A senha do usuário admin não pode ser alterada!", "error")
        return redirect(url_for('index'))

    if request.method == 'POST':
        nova_senha = request.form.get('nova_senha')
        confirmar_senha = request.form.get('confirmar_senha')

        if not nova_senha or len(nova_senha) < 6:
            flash("A senha deve ter pelo menos 6 caracteres!", "error")
            return redirect(url_for('alterar_senha'))

        if nova_senha != confirmar_senha:
            flash("As senhas não coincidem!", "error")
            return redirect(url_for('alterar_senha'))

        try:
            usuario.set_senha(nova_senha)
            db.session.commit()
            flash("Senha alterada com sucesso!", "success")
            return redirect(url_for('index'))
        except Exception as e:
            db.session.rollback()
            flash(f"Erro ao alterar senha: {str(e)}", "error")

    return render_template('alterar_senha.html')




@app.route('/gerenciar_usuarios')
def gerenciar_usuarios():
    if not session.get('admin'):
        return redirect(url_for('index'))

    usuarios = Usuario.query.filter_by(is_admin=False).order_by(Usuario.nome).all()

    print("Usuários carregados:", usuarios)  # Depuração

    return render_template('gerenciar_usuarios.html', usuarios=usuarios)



@app.route('/editar_usuario/<cpf>', methods=['GET', 'POST'])
def editar_usuario(cpf):
    if not session.get('admin'):
        return redirect(url_for('index'))

    usuario = Usuario.query.filter_by(cpf=cpf).first()

    if request.method == 'POST':
        usuario.nome = request.form['nome']
        usuario.telefone = request.form.get('telefone', '')  # Atualiza o telefone
        usuario.cpf = request.form['cpf']  # Garante que o CPF permaneça igual

        nova_senha = request.form['senha']
        if nova_senha:  # Se uma nova senha for fornecida, criptografa e atualiza
            usuario.set_senha(nova_senha)

        db.session.commit()
        return redirect(url_for('gerenciar_usuarios'))

    return render_template('editar_usuario.html', usuario=usuario)

@app.route('/deletar_usuario/<cpf>', methods=['POST'])
def deletar_usuario(cpf):
    if not session.get('admin'):
        return redirect(url_for('index'))  # Apenas admin pode deletar usuários

    usuario = Usuario.query.filter_by(cpf=cpf).first()
    if usuario:
        usuario.ativo = False
        db.session.commit()
        flash("Usuário desativado com sucesso!", "success")
    else:
        flash("Erro: Usuário não encontrado!", "error")

    return redirect(url_for('gerenciar_usuarios'))


@app.route('/alternar_usuario/<cpf>', methods=['POST'])
def alternar_usuario(cpf):
    if not session.get('admin'):
        return redirect(url_for('index'))

    usuario = Usuario.query.filter_by(cpf=cpf, is_admin=False).first()
    if not usuario:
        flash("Erro: Usuário não encontrado!", "error")
        return redirect(url_for('gerenciar_usuarios'))

    usuario.ativo = not usuario.ativo
    db.session.commit()
    flash(f"Usuário {'ativado' if usuario.ativo else 'desativado'} com sucesso!", "success")

    return redirect(url_for('gerenciar_usuarios'))

from flask import Flask, request, jsonify
from datetime import datetime
import time  # Certifique-se de importar time

@app.route('/salvar_orcamento', methods=['POST'])
def salvar_orcamento():
    try:
        # ðŸ”¹ Pegando os dados do JSON enviado pelo frontend
        data = request.json
        ids = data.get('ids')

        if not ids:
            return jsonify({"success": False, "error": "Nenhum orçamento selecionado!"}), 400

        # ðŸ”¹ Convertendo a string de IDs para uma lista de inteiros
        ids = [int(id.strip()) for id in ids.split(",") if id.strip().isdigit()]
        if not ids:
            return jsonify({"success": False, "error": "IDs inválidos!"}), 400

        # 🔹 Buscar o usuário pelo CPF salvo na sessão
        usuario = Usuario.query.filter_by(cpf=session.get('user_cpf')).first()
        criado_por = usuario.nome if usuario else "Desconhecido"  # Nome do usuário logado

        # 🔹 Gerar o código sequencial iniciando em O000100
        ultimo_orcamento = db.session.query(db.func.max(OrcamentoSalvo.id)).scalar()
        novo_codigo = f"O{(100 + (ultimo_orcamento or 0)):06d}"

        # ðŸ”¹ Data de salvamento
        data_salvamento = datetime.now(br_tz)

        # 🔹 Calcular o valor total dos orçamentos selecionados
        valor_total = db.session.query(db.func.sum(Orcamento.valor_total)).filter(Orcamento.id.in_(ids)).scalar()
        valor_total = valor_total if valor_total else 0.0
        empresa = empresa_config_dict()
        
        # 🔹 Criar o novo orçamento salvo
        novo_orcamento = OrcamentoSalvo(
            codigo=novo_codigo,
            data_salvo=data_salvamento,
            orcamentos_ids=",".join(map(str, ids)),  # IDs dos orçamentos vinculados
            valor_total=valor_total,
            criado_por=criado_por,
            prazo_entrega=int(empresa.get('prazo_entrega_padrao') or 15),
            desconto_avista=float(empresa.get('desconto_avista_padrao') or 5),
            desconto_parcelado=float(empresa.get('desconto_parcelado_padrao') or 10),
            observacoes=empresa.get('observacoes_padrao') or _config_empresa_fallback()['observacoes_padrao'],
            exclude_payments=pagamentos_excluidos_padrao(empresa),
            max_parcelas=int(empresa.get('max_parcelas_padrao') or 10),
            valor_minimo_parcela=float(empresa.get('valor_minimo_parcela') or 100),
            pagamentos_config_json=json.dumps(pagamentos_config_padrao(empresa), ensure_ascii=False),
        )

        db.session.add(novo_orcamento)
        db.session.commit()

        return jsonify({"success": True, "codigo": novo_codigo})

    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500





@app.route("/orcamentos_salvos")
def listar_orcamentos_salvos():
    user_cpf = session.get("user_cpf")
    is_admin = session.get("admin")

    orcamentos_salvos = OrcamentoSalvo.query.order_by(OrcamentoSalvo.codigo.desc()).all()

    resultado = []

    for orc_salvo in orcamentos_salvos:
        primeiro_orcamento_id = int(orc_salvo.orcamentos_ids.split(",")[0])
        primeiro_orcamento = Orcamento.query.get(primeiro_orcamento_id)

        if not primeiro_orcamento:
            continue

        cliente = Cliente.query.get(primeiro_orcamento.cliente_id)
        if not cliente:
            continue

        # Esse trecho deixa claro o filtro admin e não-admin
        if is_admin or cliente.dono == user_cpf:
            resultado.append({
                'id': orc_salvo.id,
                'codigo': orc_salvo.codigo,
                'data_salvo': orc_salvo.data_salvo,
                'valor_total': orc_salvo.valor_total,
                'criado_por': orc_salvo.criado_por,
                'status': orc_salvo.status,
                'tipo_cliente': orc_salvo.tipo_cliente,
                'cliente_nome': cliente.nome,
                'cliente_dono': cliente.dono
            })

    # Agora adicionando a clareza no filtro dos clientes:
    if is_admin:
        clientes = Cliente.query.all()
    else:
        clientes = Cliente.query.filter_by(dono=user_cpf).all()

    usuarios = Usuario.query.all()

    return render_template("orcamentos_salvos.html",
                           clientes=clientes,
                           usuarios=usuarios,
                           orcamentos=resultado)






@app.route('/detalhes_orcamento_salvo/<codigo>')
def detalhes_orcamento_salvo(codigo):
    # Verificar se o usuário está logado
    if 'user_cpf' not in session:
        flash("Você precisa fazer login para acessar esta página.", "error")
        return redirect(url_for('login'))
    
    # Buscar o orçamento salvo
    orcamento_salvo = OrcamentoSalvo.query.filter_by(codigo=codigo).first()
    
    if not orcamento_salvo:
        flash("Orçamento salvo não encontrado!", "danger")
        return redirect(url_for('listar_orcamentos_salvos'))
    
    # Verificar permissões
    usuario = Usuario.query.filter_by(cpf=session.get('user_cpf')).first()
    is_admin = session.get('admin')
    
    # Admin pode ver tudo, usuário comum só vê seus próprios orçamentos
    if not is_admin:
        ids_check = [int(i) for i in orcamento_salvo.orcamentos_ids.split(",") if i.strip()]
        tem_permissao = db.session.query(Orcamento).join(Cliente, Cliente.id == Orcamento.cliente_id).filter(
            Orcamento.id.in_(ids_check), Cliente.dono == usuario.cpf
        ).first()
        if not tem_permissao:
            flash("Você não tem permissão para acessar este orçamento!", "error")
            return redirect(url_for('listar_orcamentos_salvos'))
    
    # Buscar os orçamentos vinculados
    ids = [int(id) for id in orcamento_salvo.orcamentos_ids.split(",") if id.strip()]
    orcamentos = Orcamento.query.filter(Orcamento.id.in_(ids)).all()
    
    if not orcamentos:
        flash("Orçamento salvo não contém itens válidos!", "danger")
        return redirect(url_for('listar_orcamentos_salvos'))
    
    # Usar a função auxiliar para criar os agrupamentos
    ambientes_agrupados = recriar_agrupamentos_orcamento(codigo)
    
    # Se a função retornar None (erro), criar estrutura manualmente como fallback
    if ambientes_agrupados is None:
        ambientes_agrupados = {}
        for orcamento in orcamentos:
            ambiente_nome = orcamento.ambiente.nome if orcamento.ambiente else 'Sem Ambiente'
            
            if ambiente_nome not in ambientes_agrupados:
                ambientes_agrupados[ambiente_nome] = {}
            
            descricao_nome = orcamento.descricao.nome if orcamento.descricao else 'Sem Descrição'
            
            if descricao_nome not in ambientes_agrupados[ambiente_nome]:
                ambientes_agrupados[ambiente_nome][descricao_nome] = {}
            
            tipo_produto = orcamento.tipo_produto
            if tipo_produto not in ambientes_agrupados[ambiente_nome][descricao_nome]:
                ambientes_agrupados[ambiente_nome][descricao_nome][tipo_produto] = []
            
            ambientes_agrupados[ambiente_nome][descricao_nome][tipo_produto].append(orcamento)
    
    # Calcular valor total
    valor_total_final = sum(o.valor_total for o in orcamentos)
    valor_total_float = valor_total_final
    
    # Configurar logo URL
    logo_url = empresa_logo_data_uri()
    
    # Obter informações do usuário
    usuario_logado = Usuario.query.filter_by(cpf=session.get('user_cpf')).first()
    vendedor_nome = orcamento_salvo.criado_por or (usuario_logado.nome if usuario_logado else "")
    usuario_vendedor = Usuario.query.filter_by(nome=vendedor_nome).first() if vendedor_nome else usuario_logado
    telefone_usuario = usuario_vendedor.telefone if usuario_vendedor else ""
    
    # Obter informações do cliente do primeiro orçamento
    cliente_nome = orcamentos[0].cliente.nome if orcamentos else "Desconhecido"
    
    # Obter configurações do rodapé do orçamento salvo (com valores padrão como fallback)
    prazo_entrega = orcamento_salvo.prazo_entrega if orcamento_salvo.prazo_entrega is not None else 15
    desconto_avista = orcamento_salvo.desconto_avista if orcamento_salvo.desconto_avista is not None else 5
    desconto_parcelado = orcamento_salvo.desconto_parcelado if orcamento_salvo.desconto_parcelado is not None else 10
    observacoes = orcamento_salvo.observacoes if orcamento_salvo.observacoes is not None else "Medidas sujeitas a confirmação no local. Valores válidos por 7 dias."
    empresa = empresa_config_dict()
    max_parcelas = orcamento_salvo.max_parcelas if orcamento_salvo.max_parcelas is not None else int(empresa.get('max_parcelas_padrao') or 10)
    valor_minimo_parcela = orcamento_salvo.valor_minimo_parcela if orcamento_salvo.valor_minimo_parcela is not None else float(empresa.get('valor_minimo_parcela') or 100)
    parcelas_orcamento = calcular_parcelas_orcamento(valor_total_float, max_parcelas, valor_minimo_parcela)
    pagamentos_config = pagamentos_config_orcamento(orcamento_salvo)
    
    # Obter opções de pagamento excluídas
    exclude_payments = orcamento_salvo.exclude_payments.split(',') if orcamento_salvo.exclude_payments else []
    
    # Verificar se há parâmetros de URL para mensagens de sucesso/erro
    item_excluido = request.args.get('item_excluido')
    erro = request.args.get('erro')
    
    # Renderizar o template
    return render_template(
        "detalhes_orcamento_salvo.html",
        logo_url=logo_url,
        codigo_orcamento=orcamento_salvo.codigo,
        data_salvo=orcamento_salvo.data_salvo,
        cliente_nome=cliente_nome,
        orcamentos=orcamentos,
        ambientes_agrupados=ambientes_agrupados,
        valor_total_final="R$ {:,.2f}".format(valor_total_final).replace(",", "X").replace(".", ",").replace("X", "."),
        valor_total_float=valor_total_float,
        telefone_usuario=telefone_usuario,
        vendedor_nome=vendedor_nome,
        prazo_entrega=prazo_entrega,
        desconto_avista=desconto_avista,
        desconto_parcelado=desconto_parcelado,
        observacoes=observacoes,
        exclude_payments=exclude_payments,
        pagamentos_config=pagamentos_config,
        # Passar parâmetro para saber se estamos em modo PDF ou não
        pdf=False,
        # Passar o usuário atual para verificar permissões no template
        usuario_atual=usuario_logado,
        is_admin=is_admin,
        max_parcelas=max_parcelas,
        valor_minimo_parcela=valor_minimo_parcela,
        parcelas_orcamento=parcelas_orcamento,
        linhas_ordenadas=linhas_ordenadas_por_tabela(ambientes_agrupados, orcamento_salvo)
    )

def recriar_agrupamentos_orcamento(codigo_orcamento):
    """
    Função auxiliar para recriar os agrupamentos de um orçamento salvo.
    Estrutura: Ambiente -> Descrição -> Tipo de Produto -> Lista de Produtos
    """
    try:
        orcamento_salvo = OrcamentoSalvo.query.filter_by(codigo=codigo_orcamento).first()
        
        if not orcamento_salvo:
            print(f"âš ï¸ Orçamento salvo não encontrado: {codigo_orcamento}")
            return None
        
        # Extrair IDs dos orçamentos (com validação)
        ids_str = orcamento_salvo.orcamentos_ids
        if not ids_str or not ids_str.strip():
            print(f"âš ï¸ Lista de IDs vazia para orçamento: {codigo_orcamento}")
            return {}
        
        ids = []
        for id_str in ids_str.split(','):
            id_str = id_str.strip()
            if id_str and id_str.isdigit():
                ids.append(int(id_str))
            else:
                print(f"âš ï¸ ID inválido ignorado: '{id_str}'")
        
        if not ids:
            print(f"âš ï¸ Nenhum ID válido encontrado para orçamento: {codigo_orcamento}")
            return {}
        
        # Buscar orçamentos
        orcamentos = Orcamento.query.filter(Orcamento.id.in_(ids)).all()
        
        if not orcamentos:
            print(f"âš ï¸ Nenhum orçamento encontrado para os IDs: {ids}")
            return {}
        
        # Reagrupar por ambiente -> descrição -> tipo de produto
        ambientes_agrupados = {}
        
        for orcamento in orcamentos:
            # Obter nome do ambiente
            if orcamento.ambiente:
                ambiente_nome = orcamento.ambiente.nome
            else:
                ambiente_nome = 'Sem Ambiente'
                print(f"â„¹ï¸ Orçamento {orcamento.id} sem ambiente definido")
            
            # Inicializar o ambiente se não existir
            if ambiente_nome not in ambientes_agrupados:
                ambientes_agrupados[ambiente_nome] = {}
            
            # Obter nome da descrição
            if orcamento.descricao:
                descricao_nome = orcamento.descricao.nome
            else:
                descricao_nome = 'Sem Descrição'
                print(f"Info: orcamento {orcamento.id} sem descricao definida")
            
            # Inicializar a descrição se não existir
            if descricao_nome not in ambientes_agrupados[ambiente_nome]:
                ambientes_agrupados[ambiente_nome][descricao_nome] = {}
            
            # Obter tipo de produto
            tipo_produto = orcamento.tipo_produto
            if not tipo_produto:
                tipo_produto = 'Não especificado'
                print(f"Info: orcamento {orcamento.id} sem tipo de produto definido")
            
            # Inicializar o tipo de produto se não existir
            if tipo_produto not in ambientes_agrupados[ambiente_nome][descricao_nome]:
                ambientes_agrupados[ambiente_nome][descricao_nome][tipo_produto] = []
            
            # Adicionar o orçamento à lista correta
            ambientes_agrupados[ambiente_nome][descricao_nome][tipo_produto].append(orcamento)
        
        # Log para debug
        print(f"Agrupamentos recriados para {codigo_orcamento}:")
        for ambiente, descricoes in ambientes_agrupados.items():
            print(f"  Ambiente {ambiente}: {len(descricoes)} descricoes")
            for descricao, tipos in descricoes.items():
                print(f"    Descricao {descricao}: {len(tipos)} tipos de produto")
                total_itens = sum(len(produtos) for produtos in tipos.values())
                print(f"      Total de itens nesta descricao: {total_itens}")
        
        return ambientes_agrupados
    
    except Exception as e:
        print(f"Erro ao recriar agrupamentos para {codigo_orcamento}: {str(e)}")
        import traceback
        traceback.print_exc()
        return None

@app.route('/orcamentos_salvos')
def orcamentos_salvos():
    usuario_logado = session.get('user_cpf')  # CPF do usuário logado
    admin = session.get('admin')  # Verifica se é administrador

    # 🔹 Montando a query para buscar os orçamentos salvos corretamente
    query = db.session.query(
        OrcamentoSalvo.id,
        OrcamentoSalvo.codigo,
        OrcamentoSalvo.data_salvo,
        OrcamentoSalvo.valor_total,
        OrcamentoSalvo.criado_por,
        OrcamentoSalvo.status,
        OrcamentoSalvo.tipo_cliente,
        Cliente.nome.label("cliente_nome"),
        Cliente.dono.label("cliente_dono")  # O CPF de quem cadastrou o cliente
    ).join(Orcamento, db.func.instr(OrcamentoSalvo.orcamentos_ids, db.cast(Orcamento.id, db.String())) > 0
    ).join(Cliente, Cliente.id == Orcamento.cliente_id)

    # 🔹 Se não for admin, filtrar apenas os orçamentos dos clientes cadastrados pelo usuário logado
    if not admin:
        query = query.filter(Cliente.dono == usuario_logado)

    orcamentos = query.group_by(
        OrcamentoSalvo.id, Cliente.nome, Cliente.dono
    ).all()

    return render_template('orcamentos_salvos.html', orcamentos=orcamentos)





@app.route("/deletar_orcamento_salvo/<int:orcamento_id>", methods=["POST"])
def deletar_orcamento_salvo(orcamento_id):
    try:
        orcamento = OrcamentoSalvo.query.get(orcamento_id)
        if not orcamento:
            return jsonify({"error": "Orçamento não encontrado."}), 404

        # 🔥 CORREÇÃO: Excluir registros de remoção associados
        ItemRemovidoOrcamento.query.filter_by(
            orcamento_salvo_codigo=orcamento.codigo
        ).delete()
        
        # ðŸ”¥ Excluir desenhos associados
        DesenhoOrdemServico.query.filter_by(orcamento_salvo_codigo=orcamento.codigo).delete()
        
        # Depois exclui o orçamento salvo
        db.session.delete(orcamento)
        db.session.commit()
        
        return jsonify({"success": "Orçamento deletado com sucesso!"})
    
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Erro ao excluir orçamento: {str(e)}"}), 500

@app.route('/atualizar_status_tipo_cliente', methods=['POST'])
def atualizar_status_tipo_cliente():
    try:
        data = request.json or {}
        orcamento_id = data.get('id')
        novo_status = data.get('status')
        novo_tipo_cliente = data.get('tipo_cliente')
        valor_venda = _float_payload(data.get('valor_venda'))
        entrada_percentual = _float_payload(data.get('entrada_percentual'))
        final_percentual = _float_payload(data.get('final_percentual'))
        entrada_valor = _float_payload(data.get('entrada_valor'))
        final_valor = _float_payload(data.get('final_valor'))
        forma_pagamento = (data.get('forma_pagamento') or '').strip()
        data_fechamento = _data_payload(data.get('data_fechamento'))
        observacao_vendas = data.get('observacao_vendas')

        if not orcamento_id:
            return jsonify({"success": False, "error": "ID do orçamento não foi enviado!"}), 400

        orcamento = OrcamentoSalvo.query.get(orcamento_id)

        if not orcamento:
            return jsonify({"success": False, "error": "Orçamento não encontrado!"}), 404

        # Atualiza apenas se houver mudanças
        if novo_status and orcamento.status != novo_status:
            orcamento.status = novo_status
        if novo_tipo_cliente and orcamento.tipo_cliente != novo_tipo_cliente:
            orcamento.tipo_cliente = novo_tipo_cliente
        if novo_status == "Em Espera":
            orcamento.data_fechamento = None
        if (orcamento.status or "") in ("Aprovado", "Declinado") and "data_fechamento" not in data and not orcamento.data_fechamento:
            orcamento.data_fechamento = datetime.now(br_tz).replace(hour=0, minute=0, second=0, microsecond=0)
        if "valor_venda" in data:
            orcamento.valor_venda = valor_venda
        if "entrada_percentual" in data:
            orcamento.entrada_percentual = entrada_percentual
        if "final_percentual" in data:
            orcamento.final_percentual = final_percentual
        if "entrada_valor" in data:
            orcamento.entrada_valor = entrada_valor
        if "final_valor" in data:
            orcamento.final_valor = final_valor
        if "forma_pagamento" in data:
            orcamento.forma_pagamento = forma_pagamento
        if "data_fechamento" in data:
            if (orcamento.status or "") in ("Aprovado", "Declinado"):
                orcamento.data_fechamento = data_fechamento or datetime.now(br_tz).replace(hour=0, minute=0, second=0, microsecond=0)
            else:
                orcamento.data_fechamento = None
        if "observacao_vendas" in data:
            orcamento.observacao_vendas = observacao_vendas or None

        db.session.commit()

        dados_venda = _dados_venda_orcamento(orcamento)
        return jsonify({
            "success": True,
            "message": "Orçamento atualizado com sucesso!",
            "status": orcamento.status,
            "tipo_cliente": orcamento.tipo_cliente,
            "valor_aprovado": _moeda(_valor_venda_considerado(orcamento)),
            **dados_venda,
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
        



@app.route('/orcamento/<path:token>')
def orcamento_preview(token):
    codigo = decodificar_token_orcamento(token)
    if not codigo:
        return "Orçamento não encontrado", 404
    orc = OrcamentoSalvo.query.filter_by(codigo=codigo).first()
    if not orc:
        return "Orçamento não encontrado", 404
    valor = "R$ {:,.2f}".format(orc.valor_total).replace(",", "X").replace(".", ",").replace("X", ".")
    empresa = empresa_config_dict()
    nome_empresa = empresa.get('nome_empresa') or 'Sistema de Orçamento'
    dominio = request.url_root.rstrip('/')
    logo_url = empresa_logo_url()
    logo_absoluta = logo_url if logo_url.startswith('data:') else request.url_root.rstrip('/') + logo_url
    return f'''<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta property="og:title" content="Orçamento - {nome_empresa}">
<meta property="og:description" content="Orçamento em mármore e granito - Valor: {valor}">
<meta property="og:image" content="{logo_absoluta}">
<meta property="og:url" content="{dominio}/orcamento/{token}">
<meta property="og:type" content="website">
<title>Orçamento - {nome_empresa}</title>
<meta http-equiv="refresh" content="2;url=/gerar_pdf_orcamento/{token}">
<style>
body{{font-family:Arial,sans-serif;display:flex;justify-content:center;align-items:center;min-height:100vh;margin:0;background:#1a1a2e;color:#fff}}
.card{{text-align:center;background:#16213e;padding:50px 40px;border-radius:16px;box-shadow:0 4px 20px rgba(0,0,0,.3);max-width:400px;width:90%}}
.logo{{width:180px;margin-bottom:10px}}
.brand{{font-size:1.6rem;font-weight:bold;color:#d4a017;margin:0 0 6px;letter-spacing:1px}}
.sub{{color:#999;font-size:.85rem;margin:0 0 20px}}
.divider{{width:60px;height:2px;background:#d4a017;margin:0 auto 20px}}
h2{{color:#fff;margin:0 0 8px;font-size:1.1rem;font-weight:normal}}
.valor{{font-size:1.5rem;color:#22c55e;font-weight:bold;margin:12px 0 20px}}
a{{color:#d4a017;text-decoration:none;display:inline-block;padding:12px 30px;border:2px solid #d4a017;border-radius:8px;font-weight:bold;transition:all .2s}}
a:hover{{background:#d4a017;color:#1a1a2e}}
.redirect{{font-size:.8rem;color:#666;margin-top:16px}}
</style>
</head>
<body>
<div class="card">
{f'<img class="logo" src="{logo_absoluta}" alt="{nome_empresa}">' if not logo_absoluta.startswith('data:') else ''}
<p class="brand">{nome_empresa}</p>
<p class="sub">Mármores &amp; Granitos</p>
<div class="divider"></div>
<h2>Orçamento</h2>
<div class="valor">{valor}</div>
<a href="/gerar_pdf_orcamento/{token}">&#128196; Baixar PDF</a>
<p class="redirect">Redirecionando para o PDF...</p>
</div>
</body>
</html>'''

@app.route('/gerar_pdf_orcamento/<path:codigo_ou_token>')
def gerar_pdf_orcamento(codigo_ou_token):
    orcamento_salvo = OrcamentoSalvo.query.filter_by(codigo=codigo_ou_token).first()
    if not orcamento_salvo:
        codigo_real = decodificar_token_orcamento(codigo_ou_token)
        if codigo_real:
            orcamento_salvo = OrcamentoSalvo.query.filter_by(codigo=codigo_real).first()
    if not orcamento_salvo:
        return "Orçamento não encontrado", 404

    ids = [int(id) for id in orcamento_salvo.orcamentos_ids.split(",")]
    orcamentos = Orcamento.query.filter(Orcamento.id.in_(ids)).all()
    
    # 🔥 Estrutura de agrupamento: Ambiente -> Descrição -> Tipo de Produto
    ambientes_agrupados = {}
    for orcamento in orcamentos:
        ambiente_nome = orcamento.ambiente.nome if orcamento.ambiente else 'Sem Ambiente'
        if ambiente_nome not in ambientes_agrupados:
            ambientes_agrupados[ambiente_nome] = {}
        
        descricao_nome = orcamento.descricao.nome if orcamento.descricao else 'Sem Descrição'
        if descricao_nome not in ambientes_agrupados[ambiente_nome]:
            ambientes_agrupados[ambiente_nome][descricao_nome] = {}
        
        tipo_produto = orcamento.tipo_produto
        if tipo_produto not in ambientes_agrupados[ambiente_nome][descricao_nome]:
            ambientes_agrupados[ambiente_nome][descricao_nome][tipo_produto] = []
        
        ambientes_agrupados[ambiente_nome][descricao_nome][tipo_produto].append(orcamento)
    
    # Calcular valor total
    valor_total_final = sum(o.valor_total for o in orcamentos)
    valor_total_float = valor_total_final

    logo_url = empresa_logo_url()
    
    usuario_logado = Usuario.query.filter_by(cpf=session.get('user_cpf')).first()
    vendedor_nome = orcamento_salvo.criado_por or (usuario_logado.nome if usuario_logado else "")
    usuario_vendedor = Usuario.query.filter_by(nome=vendedor_nome).first() if vendedor_nome else usuario_logado
    if not usuario_vendedor:
        usuario_vendedor = Usuario.query.filter_by(cpf='12233344441').first()
    telefone_usuario = usuario_vendedor.telefone if usuario_vendedor else ""

    # ✅ Valores do rodapé (com fallback)
    prazo_entrega = orcamento_salvo.prazo_entrega if orcamento_salvo.prazo_entrega is not None else 15
    desconto_avista = orcamento_salvo.desconto_avista if orcamento_salvo.desconto_avista is not None else 5
    desconto_parcelado = orcamento_salvo.desconto_parcelado if orcamento_salvo.desconto_parcelado is not None else 10
    observacoes = orcamento_salvo.observacoes if orcamento_salvo.observacoes is not None else "Medidas sujeitas a confirmação no local. Valores válidos por 7 dias."
    
    # âœ… NOVO: Obter max_parcelas (pode ser None)
    empresa = empresa_config_dict()
    max_parcelas = orcamento_salvo.max_parcelas if orcamento_salvo.max_parcelas is not None else int(empresa.get('max_parcelas_padrao') or 10)
    valor_minimo_parcela = orcamento_salvo.valor_minimo_parcela if orcamento_salvo.valor_minimo_parcela is not None else float(empresa.get('valor_minimo_parcela') or 100)
    parcelas_orcamento = calcular_parcelas_orcamento(valor_total_float, max_parcelas, valor_minimo_parcela)
    pagamentos_config = pagamentos_config_orcamento(orcamento_salvo)

    # ✅ Opções excluídas
    exclude_payments = orcamento_salvo.exclude_payments.split(',') if orcamento_salvo.exclude_payments else []
    exclude_param = request.args.get('exclude_payments', '')
    if exclude_param:
        exclude_payments = exclude_param.split(',')

    # Renderizar HTML
    rendered_html = render_template(
        "detalhes_orcamento_salvo.html",
        logo_url=logo_url,
        codigo_orcamento=orcamento_salvo.codigo,
        data_salvo=orcamento_salvo.data_salvo,
        cliente_nome=orcamentos[0].cliente.nome if orcamentos else "Desconhecido",
        orcamentos=orcamentos,
        ambientes_agrupados=ambientes_agrupados,
        valor_total_final="R$ {:,.2f}".format(valor_total_final).replace(",", "X").replace(".", ",").replace("X", "."),
        valor_total_float=valor_total_float,
        telefone_usuario=telefone_usuario,
        vendedor_nome=vendedor_nome,
        prazo_entrega=prazo_entrega,
        desconto_avista=desconto_avista,
        desconto_parcelado=desconto_parcelado,
        observacoes=observacoes,
        pdf=True,
        exclude_payments=exclude_payments,
        pagamentos_config=pagamentos_config,
        max_parcelas=max_parcelas,
        valor_minimo_parcela=valor_minimo_parcela,
        parcelas_orcamento=parcelas_orcamento,
        linhas_ordenadas=linhas_ordenadas_por_tabela(ambientes_agrupados, orcamento_salvo)
    )

    try:
        pdf_bytes = _get_weasyprint_html()(string=rendered_html, base_url=request.url_root).write_pdf()
    except RuntimeError:
        pdf_bytes = _gerar_pdf_html_com_chrome(rendered_html, request.url_root)
        return _resposta_pdf(pdf_bytes, f"orcamento_{orcamento_salvo.codigo}.pdf")

    return _resposta_pdf(pdf_bytes, f"orcamento_{orcamento_salvo.codigo}.pdf")

@app.route('/orcamentos/editar_material_rt_selecionados', methods=['POST'])
def editar_material_rt_selecionados():
    data = request.get_json()
    orcamento_ids = data.get('orcamento_ids', [])
    cliente_id = data.get('cliente_id')
    material_id = data.get('material_id')
    rt = data.get('rt')
    rt_percentual = data.get('rt_percentual', 0.0)
    if rt == 'Sim' and float(rt_percentual or 0) <= 0:
        rt_percentual = float(empresa_config_dict().get('rt_percentual_padrao') or 10)
    descricao_id = data.get('descricao_id')  # 🔥 NOVO: Adicionar descrição
    produto_id = data.get('produto_id')      # ðŸ”¥ NOVO: Adicionar produto

    if not orcamento_ids:
        return jsonify({'erro': 'Nenhum orçamento selecionado.'}), 400

    # Se cliente_id foi fornecido, validar se existe
    if cliente_id:
        cliente = Cliente.query.get(cliente_id)
        if not cliente:
            return jsonify({'erro': 'Cliente não encontrado.'}), 404
    else:
        cliente = None

    # Se material_id foi fornecido, validar se existe
    if material_id:
        material = Material.query.get(material_id)
        if not material:
            return jsonify({'erro': 'Material não encontrado.'}), 404
    else:
        material = None

    # Se descricao_id foi fornecido, validar se existe
    if descricao_id:
        descricao = Descricao.query.get(descricao_id)
        if not descricao:
            return jsonify({'erro': 'Descrição não encontrada.'}), 404
    else:
        descricao = None

    # Se produto_id foi fornecido, validar se existe
    if produto_id:
        produto = Produto.query.get(produto_id)
        if not produto:
            return jsonify({'erro': 'Produto não encontrado.'}), 404
    else:
        produto = None

    cuba_valores = {
        'Embutida': 225,
        'Esculpida': 175,
        'Tradicional Inox': 225,
        'Tanque Inox': 500,
        'Apoio Cliente': 125,
        'Embutida Cliente': 125,
        'Gourmet Cliente': 225,
        'Sobrepor Cliente': 125,
        'Tanque Inox Cliente': 225
    }

    cooktop_valor = 50  # Valor fixo para cooktop

    orcamentos = Orcamento.query.filter(Orcamento.id.in_(orcamento_ids)).all()

    for orcamento in orcamentos:
        # Atualizar cliente apenas se foi fornecido
        if cliente_id:
            orcamento.cliente_id = cliente_id
        
        # Atualizar material apenas se foi fornecido
        if material_id:
            orcamento.material_id = material_id
            material_para_calculo = material
        else:
            material_para_calculo = orcamento.material
        
        # 🔥 NOVO: Atualizar descrição apenas se foi fornecida
        if descricao_id:
            orcamento.descricao_id = descricao_id
        
        # ðŸ”¥ NOVO: Atualizar produto apenas se foi fornecido
        if produto_id:
            orcamento.produto_id = produto_id
        
        # Atualizar RT apenas se foi fornecida
        if rt is not None:
            orcamento.rt = rt
        
        # Atualizar percentual RT apenas se RT for "Sim"
        if rt == 'Sim':
            orcamento.rt_percentual = rt_percentual
        elif rt is None:
            # Manter o percentual atual se RT não foi alterada
            pass
        else:
            # Se RT foi definida como "Não", zerar o percentual
            orcamento.rt_percentual = 0.0

        valor_total_criar = 0

        comprimento_cal = max(orcamento.comprimento, 10)
        largura_cal = max(orcamento.largura, 10)

        valor_base = material_para_calculo.valor * (comprimento_cal * largura_cal / 10000)

        if orcamento.tipo_produto in ['Bancada', 'Lavatorio']:
            if material_para_calculo.valor < 1000:
                valor_base *= 1.3
            elif material_para_calculo.valor < 2000:
                valor_base *= 1.15
            elif material_para_calculo.valor < 1000000:
                valor_base *= 1.1

        if orcamento.tipo_produto in ['Ilharga Bipolida', 'Pedra Bipolida com Saia', 'Pedra Bipolida'] and material_para_calculo.valor < 1000000:
            pricing_opts = opcoes_precificacao_empresa()
            margem_bipolida = pricing_opts.get('ilharga_bipolida_margem', 15)
            if orcamento.tipo_produto == 'Pedra Bipolida com Saia':
                margem_bipolida = pricing_opts.get('pedra_bipolida_com_saia_margem', 15)
            elif orcamento.tipo_produto == 'Pedra Bipolida':
                margem_bipolida = pricing_opts.get('pedra_bipolida_margem', 15)
            valor_base *= 1 + (float(margem_bipolida or 0) / 100)

        valor_total_criar += valor_base

        # Nicho
        if orcamento.tipo_produto == 'Nicho':
            profundidade_nicho = max(orcamento.profundidade_nicho or 0, 10)
            if orcamento.tem_fundo == 'Sim':
                area_nicho = ((comprimento_cal + 4) * (largura_cal + 4)) + (2 * (comprimento_cal + 4) * profundidade_nicho) + (2 * (largura_cal +4) * profundidade_nicho)
            else:
                area_nicho = 2 * ((comprimento_cal + 4) + (largura_cal + 4)) * profundidade_nicho

            if orcamento.tem_alisar == 'Sim' and (orcamento.largura_alisar or 0) > 0:
                largura_alisar_cal = 10 if 0 < orcamento.largura_alisar < 10 else orcamento.largura_alisar
                area_nicho += ((comprimento_cal + (largura_alisar_cal * 2)) * largura_alisar_cal * 2) + \
                              ((largura_cal + (largura_alisar_cal * 2)) * largura_alisar_cal * 2)

            valor_nicho = (area_nicho / 10000) * material_para_calculo.valor + 150
            valor_total_criar = valor_nicho

        # Saia
        if orcamento.tipo_produto in ['Ilharga', 'Ilharga Bipolida', 'Pedra Simples com Saia', 'Pedra Bipolida com Saia', 'Bancada', 'Lavatorio']:
            comprimento_saia_cal = 10 if 0 < orcamento.comprimento_saia < 10 else orcamento.comprimento_saia
            largura_saia_cal = 10 if 0 < orcamento.largura_saia < 10 else orcamento.largura_saia
            valor_saia = comprimento_saia_cal * largura_saia_cal * material_para_calculo.valor / 10000
            valor_total_criar += valor_saia

        # Fronte
        if orcamento.tipo_produto in ['Bancada', 'Lavatorio']:
            comprimento_fronte_cal = 10 if 0 < orcamento.comprimento_fronte < 10 else orcamento.comprimento_fronte
            largura_fronte_cal = 10 if 0 < orcamento.largura_fronte < 10 else orcamento.largura_fronte
            valor_fronte = comprimento_fronte_cal * largura_fronte_cal * material_para_calculo.valor / 10000
            valor_total_criar += valor_fronte

        # Pedra de Box
        if orcamento.tipo_produto == 'Pedra de Box':
            pricing_opts = opcoes_precificacao_empresa()
            valor_total_criar = (valor_base * 2) + ((orcamento.comprimento or 0) / 100) * pricing_opts.get('pedra_box_adicional', 30)

        # Cubas
        if orcamento.tipo_cuba:
            valor_cuba = cuba_valores.get(orcamento.tipo_cuba, 0)
            valor_total_criar += valor_cuba * (orcamento.quantidade_cubas or 0)

            if orcamento.tipo_cuba == 'Esculpida':
                comprimento_cuba = orcamento.comprimento_cuba or 0
                largura_cuba = orcamento.largura_cuba or 0
                profundidade_cuba = orcamento.profundidade_cuba or 0
                if orcamento.modelo_cuba == 'Prainha':
                    m2_cuba = ((comprimento_cuba * largura_cuba) + (2 * largura_cuba * profundidade_cuba)) / 10000
                else:
                    m2_cuba = ((comprimento_cuba * largura_cuba * 2) +
                               (2 * (comprimento_cuba + largura_cuba) * profundidade_cuba)) / 10000

                valor_cuba_esculpida = m2_cuba * material_para_calculo.valor * (orcamento.quantidade_cubas or 1) 
                valor_total_criar += valor_cuba_esculpida

        # Cooktop
        if orcamento.tem_cooktop == 'Sim':
            valor_total_criar += cooktop_valor

        # 🔥 CORREÇÃO: ADICIONAR INSTALAÇÃO AQUI - ANTES DA MULTIPLICAÇÃO POR QUANTIDADE
        if orcamento.instalacao == 'Sim':
            valor_total_criar += orcamento.instalacao_valor or 0

        # Quantidade - MULTIPLICAR APÓS TODOS OS ACréSCIMOS
        valor_total_criar *= orcamento.quantidade

        # RT - usar os valores atuais ou novos
        rt_para_calculo = rt if rt is not None else orcamento.rt
        rt_percentual_para_calculo = rt_percentual if rt == 'Sim' else orcamento.rt_percentual

        if rt_para_calculo == 'Sim' and rt_percentual_para_calculo > 0:
            valor_rt = valor_total_criar / (1 - rt_percentual_para_calculo / 100) - valor_total_criar
            valor_total_final = valor_total_criar + valor_rt
        else:
            valor_total_final = valor_total_criar

        orcamento.valor_total = calcular_valor_item(
            tipo_produto=orcamento.tipo_produto,
            valor_material=material_para_calculo.valor,
            quantidade=orcamento.quantidade,
            comprimento=orcamento.comprimento,
            largura=orcamento.largura,
            instalacao=orcamento.instalacao,
            instalacao_valor=orcamento.instalacao_valor,
            rt=rt_para_calculo,
            rt_percentual=rt_percentual_para_calculo,
            comprimento_saia=orcamento.comprimento_saia,
            largura_saia=orcamento.largura_saia,
            comprimento_fronte=orcamento.comprimento_fronte,
            largura_fronte=orcamento.largura_fronte,
            tipo_cuba=orcamento.tipo_cuba,
            quantidade_cubas=orcamento.quantidade_cubas,
            comprimento_cuba=orcamento.comprimento_cuba,
            largura_cuba=orcamento.largura_cuba,
            profundidade_cuba=orcamento.profundidade_cuba,
            modelo_cuba=orcamento.modelo_cuba,
            tem_cooktop=orcamento.tem_cooktop,
            acessorios_valor_total=acessorios_total(acessorios_do_orcamento(orcamento)),
            profundidade_nicho=orcamento.profundidade_nicho,
            tem_fundo=orcamento.tem_fundo,
            tem_alisar=orcamento.tem_alisar,
            largura_alisar=orcamento.largura_alisar,
            **opcoes_precificacao_empresa(),
        )

    db.session.commit()

    # 🔥 Atualizar todos os orçamentos salvos afetados
    orcamentos_salvos = OrcamentoSalvo.query.filter(
        db.or_(*[OrcamentoSalvo.orcamentos_ids.like(f"%{id}%") for id in orcamento_ids])
    ).all()

    for orcamento_salvo in orcamentos_salvos:
        atualizar_valor_orcamento_salvo(orcamento_salvo.id)

    return jsonify({'success': 'Cliente, materiais, descrição, produto e RT atualizados, valores recalculados e orçamentos salvos atualizados.'})


@app.route('/orcamentos/duplicar_selecionados', methods=['POST'])
def duplicar_selecionados():
    data = request.get_json()
    orcamento_ids = data.get('orcamento_ids', [])

    if not orcamento_ids:
        return jsonify({'success': False, 'error': 'Nenhum orçamento selecionado.'}), 400

    try:
        novos_ids = []  # 🔥 ARMazenar os IDs dos novos orçamentos
        
        for id in orcamento_ids:
            original = Orcamento.query.get(id)
            if original:
                material = Material.query.get(original.material_id)
                valor_total = calcular_valor_item(
                    tipo_produto=original.tipo_produto,
                    valor_material=material.valor if material else 0,
                    quantidade=original.quantidade,
                    comprimento=original.comprimento,
                    largura=original.largura,
                    instalacao=original.instalacao or "Não",
                    instalacao_valor=original.instalacao_valor or 0,
                    rt=original.rt,
                    rt_percentual=original.rt_percentual,
                    comprimento_saia=original.comprimento_saia,
                    largura_saia=original.largura_saia,
                    comprimento_fronte=original.comprimento_fronte,
                    largura_fronte=original.largura_fronte,
                    tipo_cuba=original.tipo_cuba,
                    quantidade_cubas=original.quantidade_cubas,
                    comprimento_cuba=original.comprimento_cuba,
                    largura_cuba=original.largura_cuba,
                    profundidade_cuba=original.profundidade_cuba,
                    modelo_cuba=original.modelo_cuba or "Normal",
                    tem_cooktop=original.tem_cooktop,
                    acessorios_valor_total=acessorios_total(acessorios_do_orcamento(original)),
                    profundidade_nicho=original.profundidade_nicho,
                    tem_fundo=original.tem_fundo,
                    tem_alisar=original.tem_alisar,
                    largura_alisar=original.largura_alisar,
                    **opcoes_precificacao_empresa(),
                )

                novo_orcamento = Orcamento(
                    cliente_id=original.cliente_id,
                    ambiente_id=original.ambiente_id,
                    descricao_id=original.descricao_id,  # 🔥 ADICIONAR DESCRIÇÃO
                    produto_id=original.produto_id,      # ðŸ”¥ ADICIONAR PRODUTO
                    tipo_produto=original.tipo_produto,
                    material_id=original.material_id,
                    quantidade=original.quantidade,
                    comprimento=original.comprimento,
                    largura=original.largura,
                    instalacao=original.instalacao or "Não",
                    instalacao_valor=original.instalacao_valor or 0,
                    rt=original.rt,
                    rt_percentual=original.rt_percentual,
                    comprimento_saia=original.comprimento_saia,
                    largura_saia=original.largura_saia,
                    comprimento_fronte=original.comprimento_fronte,
                    largura_fronte=original.largura_fronte,
                    tipo_cuba=original.tipo_cuba,
                    quantidade_cubas=original.quantidade_cubas,
                    modelo_cuba=original.modelo_cuba,
                    comprimento_cuba=original.comprimento_cuba,
                    largura_cuba=original.largura_cuba,
                    profundidade_cuba=original.profundidade_cuba,
                    tem_cooktop=original.tem_cooktop,
                    acessorios_json=original.acessorios_json,
                    profundidade_nicho=original.profundidade_nicho,
                    tem_fundo=original.tem_fundo,
                    tem_alisar=original.tem_alisar,
                    largura_alisar=original.largura_alisar,
                    valor_total=valor_total,
                    dono=original.dono,
                    data=datetime.now(br_tz)
                )

                db.session.add(novo_orcamento)
                db.session.flush()  # 🔥 Para obter o ID do novo orçamento
                novos_ids.append(novo_orcamento.id)

        db.session.commit()
        
        # ðŸ”¥ RETORNAR OS NOVOS IDs PARA SELEÇÃO AUTOMÁTICA
        return jsonify({
            'success': True, 
            'novos_ids': novos_ids,
            'quantidade': len(novos_ids)
        })

    except Exception as e:
        db.session.rollback()
        import traceback
        return jsonify({'success': False, 'error': traceback.format_exc()}), 500


@app.route('/salvar_rodape_orcamento/<codigo>', methods=['POST'])
def salvar_rodape_orcamento(codigo):
    orcamento_salvo = OrcamentoSalvo.query.filter_by(codigo=codigo).first()
    ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    
    if not orcamento_salvo:
        if ajax:
            return jsonify({'success': False, 'message': 'Orçamento salvo não encontrado!'}), 404
        flash("Orçamento salvo não encontrado!", "danger")
        return redirect(url_for('listar_orcamentos_salvos'))
    
    # Atualizar os valores do rodapé
    orcamento_salvo.prazo_entrega = int(request.form.get('prazo_entrega', 15))
    orcamento_salvo.desconto_avista = float(request.form.get('desconto_avista', 5))
    orcamento_salvo.desconto_parcelado = float(request.form.get('desconto_parcelado', 10))
    orcamento_salvo.observacoes = request.form.get('observacoes', '')
    
    # ✅ NOVO: Salvar o número máximo de parcelas (pode ser vazio)
    max_parcelas = request.form.get('max_parcelas', '')
    orcamento_salvo.max_parcelas = int(max_parcelas) if max_parcelas.strip() else None
    valor_minimo_parcela = request.form.get('valor_minimo_parcela', '')
    orcamento_salvo.valor_minimo_parcela = float(valor_minimo_parcela) if valor_minimo_parcela.strip() else None
    
    # ✅ Salvar as opções de pagamento excluídas
    exclude_payments = request.form.get('exclude_payments', '')
    orcamento_salvo.exclude_payments = exclude_payments
    
    db.session.commit()
    if ajax:
        return jsonify({'success': True})

    flash("Rodapé do orçamento salvo com sucesso!", "success")
    
    return redirect(url_for('detalhes_orcamento_salvo', codigo=codigo))


@app.route('/salvar_ordem_linhas_orcamento/<codigo>', methods=['POST'])
def salvar_ordem_linhas_orcamento(codigo):
    orcamento_salvo = OrcamentoSalvo.query.filter_by(codigo=codigo).first()
    if not orcamento_salvo:
        return jsonify({'success': False, 'message': 'Orçamento salvo não encontrado.'}), 404

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        try:
            data = json.loads((request.get_data(as_text=True) or '').strip() or '{}')
        except (TypeError, ValueError):
            data = {}
    tabelas = data.get('tables')
    chave = str(data.get('table_key') or '').strip()
    item_ids = data.get('item_ids') or []

    if tabelas is None:
        if not chave or not isinstance(item_ids, list):
            return jsonify({'success': False, 'message': 'Dados de ordenação inválidos.'}), 400
        tabelas = {chave: item_ids}

    if not isinstance(tabelas, dict):
        return jsonify({'success': False, 'message': 'Dados de ordenação inválidos.'}), 400

    ids_orcamento = {
        int(item_id)
        for item_id in (orcamento_salvo.orcamentos_ids or '').split(',')
        if str(item_id).strip().isdigit()
    }

    ordem_atual = ordem_linhas_orcamento(orcamento_salvo)
    for chave_tabela, ids_tabela in tabelas.items():
        chave_limpa = str(chave_tabela or '').strip()
        if not chave_limpa or not isinstance(ids_tabela, list):
            continue

        ids_limpos = []
        for item_id in ids_tabela:
            try:
                item_int = int(item_id)
            except (TypeError, ValueError):
                continue
            if item_int in ids_orcamento and item_int not in ids_limpos:
                ids_limpos.append(item_int)

        ordem_atual[chave_limpa] = ids_limpos

    orcamento_salvo.ordem_linhas_json = json.dumps(ordem_atual, ensure_ascii=False)
    db.session.commit()
    return jsonify({'success': True, 'ordem_linhas': ordem_atual})


@app.route('/adicionar_ambiente', methods=['POST'])
def adicionar_ambiente():
    try:
        data = request.get_json()
        nome = data.get('nome')
        
        if not nome:
            return jsonify({'success': False, 'message': 'Nome do ambiente é obrigatório.'}), 400
        
        user_cpf = session.get('user_cpf')
        
        # Verifica se já existe um ambiente com o mesmo nome PARA ESTE USUÁRIO
        ambiente_existente = Ambiente.query.filter_by(nome=nome, dono=user_cpf).first()
        
        if ambiente_existente:
            return jsonify({'success': False, 'message': 'Já existe um ambiente com este nome para o seu usuário.'}), 400
        
        novo_ambiente = Ambiente(nome=nome, dono=user_cpf)
        db.session.add(novo_ambiente)
        db.session.commit()
        
        return jsonify({'success': True, 'ambiente_id': novo_ambiente.id})
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/deletar_ambiente', methods=['POST'])
def deletar_ambiente():
    try:
        data = request.get_json()
        ambiente_id = data.get('ambiente_id')
        
        if not ambiente_id:
            return jsonify({'success': False, 'message': 'ID do ambiente é obrigatório.'}), 400
        
        user_cpf = session.get('user_cpf')
        ambiente = Ambiente.query.filter_by(id=ambiente_id, dono=user_cpf).first()
        
        if not ambiente:
            return jsonify({'success': False, 'message': 'Ambiente não encontrado ou você não tem permissão para excluí-lo.'}), 404
        
        orcamentos_com_ambiente = Orcamento.query.filter_by(ambiente_id=ambiente_id).count()
        if orcamentos_com_ambiente > 0:
            return jsonify({'success': False, 'message': 'Este ambiente está em uso e não pode ser excluído.'}), 400
        
        db.session.delete(ambiente)
        db.session.commit()
        
        return jsonify({'success': True})
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/adicionar_descricao', methods=['POST'])
def adicionar_descricao():
    try:
        data = request.get_json()
        nome = data.get('nome')
        
        if not nome:
            return jsonify({'success': False, 'message': 'Nome da descrição é obrigatório.'}), 400
        
        user_cpf = session.get('user_cpf')
        
        # Verifica se já existe uma descrição com o mesmo nome PARA ESTE USUÁRIO
        descricao_existente = Descricao.query.filter_by(nome=nome, dono=user_cpf).first()
        
        if descricao_existente:
            return jsonify({'success': False, 'message': 'Já existe uma descrição com este nome para o seu usuário.'}), 400
        
        nova_descricao = Descricao(nome=nome, dono=user_cpf)
        db.session.add(nova_descricao)
        db.session.commit()
        
        return jsonify({'success': True, 'descricao_id': nova_descricao.id})
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/deletar_descricao', methods=['POST'])
def deletar_descricao():
    try:
        data = request.get_json()
        descricao_id = data.get('descricao_id')
        
        if not descricao_id:
            return jsonify({'success': False, 'message': 'ID da descrição é obrigatório.'}), 400
        
        user_cpf = session.get('user_cpf')
        descricao = Descricao.query.filter_by(id=descricao_id, dono=user_cpf).first()
        
        if not descricao:
            return jsonify({'success': False, 'message': 'Descrição não encontrada ou você não tem permissão para excluí-la.'}), 404
        
        orcamentos_com_descricao = Orcamento.query.filter_by(descricao_id=descricao_id).count()
        if orcamentos_com_descricao > 0:
            return jsonify({'success': False, 'message': 'Esta descrição está em uso e não pode ser excluída.'}), 400
        
        db.session.delete(descricao)
        db.session.commit()
        
        return jsonify({'success': True})
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/adicionar_produto', methods=['POST'])
def adicionar_produto():
    try:
        data = request.get_json()
        nome = data.get('nome')
        
        if not nome:
            return jsonify({'success': False, 'message': 'Nome do produto é obrigatório.'}), 400
        
        user_cpf = session.get('user_cpf')
        
        # Verifica se já existe um produto com o mesmo nome PARA ESTE USUÁRIO
        produto_existente = Produto.query.filter_by(nome=nome, dono=user_cpf).first()
        
        if produto_existente:
            return jsonify({'success': False, 'message': 'Já existe um produto com este nome para o seu usuário.'}), 400
        
        novo_produto = Produto(nome=nome, dono=user_cpf)
        db.session.add(novo_produto)
        db.session.commit()
        
        return jsonify({'success': True, 'produto_id': novo_produto.id})
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/deletar_produto', methods=['POST'])
def deletar_produto():
    try:
        data = request.get_json()
        produto_id = data.get('produto_id')
        
        if not produto_id:
            return jsonify({'success': False, 'message': 'ID do produto é obrigatório.'}), 400
        
        user_cpf = session.get('user_cpf')
        produto = Produto.query.filter_by(id=produto_id, dono=user_cpf).first()
        
        if not produto:
            return jsonify({'success': False, 'message': 'Produto não encontrado ou você não tem permissão para excluí-lo.'}), 404
        
        orcamentos_com_produto = Orcamento.query.filter_by(produto_id=produto_id).count()
        if orcamentos_com_produto > 0:
            return jsonify({'success': False, 'message': 'Este produto está em uso e não pode ser excluído.'}), 400
        
        db.session.delete(produto)
        db.session.commit()
        
        return jsonify({'success': True})
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/orcamentos/verificar_mesmo_cliente', methods=['POST'])
def verificar_mesmo_cliente():
    try:
        data = request.get_json()
        orcamento_ids = data.get('orcamento_ids', [])
        
        if not orcamento_ids:
            return jsonify({'success': True, 'mesmo_cliente': True, 'cliente_nome': ''})
        
        # Buscar os orçamentos
        orcamentos = Orcamento.query.filter(Orcamento.id.in_(orcamento_ids)).all()
        
        if not orcamentos:
            return jsonify({'success': True, 'mesmo_cliente': True, 'cliente_nome': ''})
        
        # Verificar se todos têm o mesmo cliente
        primeiro_cliente_id = orcamentos[0].cliente_id
        mesmo_cliente = all(orc.cliente_id == primeiro_cliente_id for orc in orcamentos)
        
        cliente_nome = orcamentos[0].cliente.nome if mesmo_cliente and orcamentos[0].cliente else ''
        
        return jsonify({
            'success': True, 
            'mesmo_cliente': mesmo_cliente, 
            'cliente_nome': cliente_nome
        })
        
    except Exception as e:
        print(f"Erro em verificar_mesmo_cliente: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/orcamentos/json', methods=['GET'])
def orcamentos_json():
    try:
        user_cpf = session.get('user_cpf')
        is_admin = session.get('admin')
        
        # Obter parâmetros de filtro
        filtro_cliente = request.args.get('filtro_cliente', 'Todos')
        filtro_data_inicio = request.args.get('filtro_data_inicio', '')
        filtro_data_fim = request.args.get('filtro_data_fim', '')
        limite = request.args.get('limite', '15')
        
        # Converter limite para inteiro
        try:
            if limite == '0' or limite.lower() == 'all':
                limite_int = 0
            else:
                limite_int = int(limite)
        except (ValueError, TypeError):
            limite_int = 15

        # 🔥 CORREÇÃO: Query corrigida com outerjoins adequados
        query_base = db.session.query(
            Orcamento,
            Usuario.nome.label('nome_usuario'),
            Cliente.nome.label('cliente_nome'),
            Ambiente.nome.label('ambiente_nome'),
            Descricao.nome.label('descricao_nome'),
            Produto.nome.label('produto_nome'),
            Material.nome.label('material_nome'),
            Material.valor.label('valor_material')  # ðŸ”¥ ADICIONADO: valor do material
        ).join(Usuario, Orcamento.dono == Usuario.cpf)\
         .join(Cliente, Orcamento.cliente_id == Cliente.id)\
         .join(Material, Orcamento.material_id == Material.id)\
         .outerjoin(Ambiente, Orcamento.ambiente_id == Ambiente.id)\
         .outerjoin(Descricao, Orcamento.descricao_id == Descricao.id)\
         .outerjoin(Produto, Orcamento.produto_id == Produto.id)

        # Aplicar filtro de usuário se não for admin
        if not is_admin:
            query_base = query_base.filter(Orcamento.dono == user_cpf)

        # Aplicar filtros adicionais
        if filtro_cliente != 'Todos':
            query_base = query_base.filter(Cliente.nome == filtro_cliente)
        
        if filtro_data_inicio:
            try:
                data_inicio = datetime.strptime(filtro_data_inicio, '%Y-%m-%d')
                query_base = query_base.filter(Orcamento.data >= data_inicio)
            except ValueError:
                pass
        
        if filtro_data_fim:
            try:
                data_fim = datetime.strptime(filtro_data_fim, '%Y-%m-%d')
                data_fim = data_fim.replace(hour=23, minute=59, second=59)
                query_base = query_base.filter(Orcamento.data <= data_fim)
            except ValueError:
                pass

        # Ordenar e limitar
        query_base = query_base.order_by(Orcamento.data.desc())
        
        if limite_int > 0:
            query_base = query_base.limit(limite_int)

        orcamentos_data = query_base.all()

        # Formatar dados para JSON
        orcamentos_json = []
        for row in orcamentos_data:
            orcamento = row[0]  # Primeiro elemento é o objeto Orcamento
            
            orcamentos_json.append({
                'id': orcamento.id,
                'cliente_nome': row.cliente_nome if hasattr(row, 'cliente_nome') else '',
                'ambiente_nome': row.ambiente_nome if hasattr(row, 'ambiente_nome') and row.ambiente_nome else 'Não definido',
                'descricao_nome': row.descricao_nome if hasattr(row, 'descricao_nome') and row.descricao_nome else 'Não definido',
                'produto_nome': row.produto_nome if hasattr(row, 'produto_nome') and row.produto_nome else 'Não definido',
                'tipo_produto': orcamento.tipo_produto,
                'material_nome': row.material_nome if hasattr(row, 'material_nome') else '',
                'valor_material': row.valor_material if hasattr(row, 'valor_material') else 0,  # ðŸ”¥ NOVO
                'quantidade': orcamento.quantidade,
                'comprimento': orcamento.comprimento,
                'largura': orcamento.largura,
                'recortes': acessorios_texto(orcamento),
                'instalacao': orcamento.instalacao,
                'instalacao_valor': orcamento.instalacao_valor,  # ðŸ”¥ NOVO
                'rt_percentual': orcamento.rt_percentual,  # ðŸ”¥ NOVO
                'valor_total': orcamento.valor_total,
                'data': orcamento.data.strftime('%d-%m-%y') if orcamento.data else '',
                'nome_usuario': row.nome_usuario if hasattr(row, 'nome_usuario') else '',
                'data_attr': orcamento.data.strftime('%Y-%m-%d %H:%M:%S') if orcamento.data else ''
            })

        return jsonify({
            'success': True,
            'orcamentos': orcamentos_json,
            'total': len(orcamentos_json)
        })

    except Exception as e:
        import traceback
        print(f"âŒ Erro em /orcamentos/json: {str(e)}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/ordens_servico')
def ordens_servico():
    user_cpf = session.get("user_cpf")
    is_admin = session.get("admin")

    orcamentos_salvos = OrcamentoSalvo.query.order_by(OrcamentoSalvo.codigo.desc()).all()

    resultado = []

    for orc_salvo in orcamentos_salvos:
        primeiro_orcamento_id = int(orc_salvo.orcamentos_ids.split(",")[0])
        primeiro_orcamento = Orcamento.query.get(primeiro_orcamento_id)

        if not primeiro_orcamento:
            continue

        cliente = Cliente.query.get(primeiro_orcamento.cliente_id)
        if not cliente:
            continue

        if is_admin or cliente.dono == user_cpf:
            resultado.append({
                'id': orc_salvo.id,
                'codigo': orc_salvo.codigo,
                'data_salvo': orc_salvo.data_salvo,
                'valor_total': orc_salvo.valor_total,
                'criado_por': orc_salvo.criado_por,
                'status': orc_salvo.status,
                'tipo_cliente': orc_salvo.tipo_cliente,
                'cliente_nome': cliente.nome,
                'cliente_dono': cliente.dono
            })

    if is_admin:
        clientes = Cliente.query.all()
    else:
        clientes = Cliente.query.filter_by(dono=user_cpf).all()

    usuarios = Usuario.query.all()

    return render_template("ordens_servico.html",
                           clientes=clientes,
                           usuarios=usuarios,
                           orcamentos=resultado)



@app.route('/salvar_desenho_ordem_servico/<codigo>', methods=['POST'])
def salvar_desenho_ordem_servico(codigo):
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "Nenhum dado JSON recebido"}), 400

        desenho_data = data.get('drawingAreaHTML')

        if not desenho_data:
            return jsonify({"success": False, "error": "Dados do desenho não fornecidos"}), 400

        if _eh_imagem_configurador(desenho_data):
            return jsonify({
                "success": False,
                "error": "A ordem de serviço deve salvar HTML editável, não imagem do configurador 3D."
            }), 400

        print(f"💾 Salvando desenho editável da OS para orçamento: {codigo}")

        orcamento_salvo = OrcamentoSalvo.query.filter_by(codigo=codigo).first()
        if not orcamento_salvo:
            return jsonify({"success": False, "error": "Orçamento salvo não encontrado"}), 404

        # IMPORTANTE:
        # A tabela DesenhoOrdemServico é reservada para desenhos/imagens gerados pelo
        # fluxo público "Gere seu Orçamento" do configurador 3D. É essa tabela que
        # habilita o botão azul "Ver Desenho" na lista de orçamentos salvos.
        # Ao salvar a tela Detalhes Ordem de Serviço, gravamos somente o HTML editável
        # no próprio OrcamentoSalvo para não criar botão azul indevido.
        orcamento_salvo.desenho_ordem_servico = desenho_data

        db.session.commit()
        print("✅ Desenho editável da OS salvo sem alterar o desenho do configurador")

        return jsonify({"success": True, "message": "Desenho salvo com sucesso"})

    except Exception as e:
        db.session.rollback()
        print(f"âŒ Erro ao salvar desenho: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/detalhes_ordem_servico/<codigo>')
def detalhes_ordem_servico(codigo):
    # 🔥 VERIFICAÇÃO DE LOGIN - IMPEDIR ACESSO SEM LOGIN
    if 'user_cpf' not in session:
        flash("Você precisa fazer login para acessar esta página.", "error")
        return redirect(url_for('login'))

    # ðŸ”¥ OBTER DADOS DO USUÁRIO LOGADO
    user_cpf = session.get('user_cpf')
    is_admin = session.get('admin')

    # 🔥 BUSCAR ORÇAMENTO SALVO
    orcamento_salvo = OrcamentoSalvo.query.filter_by(codigo=codigo).first()

    if not orcamento_salvo:
        flash("Ordem de serviço não encontrada!", "danger")
        return redirect(url_for('ordens_servico'))

    # 🔥 BUSCAR ORÇAMENTOS VINCULADOS
    ids = [int(id) for id in orcamento_salvo.orcamentos_ids.split(",")]
    orcamentos = Orcamento.query.filter(Orcamento.id.in_(ids)).all()
    
    if not orcamentos:
        flash("Ordem de serviço não contém orçamentos!", "danger")
        return redirect(url_for('ordens_servico'))
    
    # ðŸ”¥ VERIFICAÇÃO DE PERMISSÃO - USUÁRIO PODE VER ESTA ORDEM?
    cliente = orcamentos[0].cliente
    
    # Admin pode ver tudo, usuário comum só vê seus próprios clientes
    if not is_admin and cliente.dono != user_cpf:
        flash("Você não tem permissão para acessar esta ordem de serviço.", "error")
        return redirect(url_for('ordens_servico'))

    # 🔥 AGRUPAR POR MATERIAL (SUA LÓGICA ORIGINAL)
    materiais_agrupados = {}
    for orcamento in orcamentos:
        material_nome = orcamento.material.nome if orcamento.material else 'Sem Material'

        if material_nome not in materiais_agrupados:
            materiais_agrupados[material_nome] = []

        materiais_agrupados[material_nome].append(orcamento)

    # Dados serializados com segurança para o JavaScript da tela de desenho.
    # Isso evita quebra na geração de peças quando nomes têm aspas, caracteres especiais
    # ou quando o orçamento vem do configurador 3D.
    grupos_pecas_json = {}
    for material_nome, produtos in materiais_agrupados.items():
        grupos_pecas_json[material_nome] = []
        for produto in produtos:
            grupos_pecas_json[material_nome].append({
                'id': produto.id,
                'tipo': produto.tipo_produto or '',
                'comprimento': produto.comprimento or 0,
                'largura': produto.largura or 0,
                'material': produto.material.nome if produto.material else material_nome,
                'quantidade': produto.quantidade or 1,
                'comprimento_saia': produto.comprimento_saia or 0,
                'largura_saia': produto.largura_saia or 0,
                'comprimento_fronte': produto.comprimento_fronte or 0,
                'largura_fronte': produto.largura_fronte or 0,
                'profundidade_nicho': produto.profundidade_nicho or 0
            })

    logo_url = empresa_logo_url()

    usuario = Usuario.query.filter_by(cpf=user_cpf).first()
    telefone_usuario = usuario.telefone if usuario else ""

    # ðŸ”¥ CARREGAR SOMENTE HTML EDITÁVEL DA ORDEM DE SERVIÇO
    # O configurador 3D salva imagem data:image/... em DesenhoOrdemServico para o botão azul
    # "Ver Desenho". Essa imagem não pode ser colocada como innerHTML na OS.
    desenho_salvo = None
    if _eh_html_ordem_servico(orcamento_salvo.desenho_ordem_servico):
        desenho_salvo = orcamento_salvo.desenho_ordem_servico
    else:
        desenho_registro = DesenhoOrdemServico.query.filter_by(
            orcamento_salvo_codigo=codigo
        ).order_by(DesenhoOrdemServico.data_criacao.desc()).first()

        # Compatibilidade com registros antigos que, por erro, salvaram HTML editável
        # na tabela do configurador. Imagens do configurador são ignoradas aqui.
        if desenho_registro and _eh_html_ordem_servico(desenho_registro.desenho_data):
            desenho_salvo = desenho_registro.desenho_data

    # ðŸ”¥ RENDERIZAR TEMPLATE COM TODOS OS DADOS
    return render_template(
        "detalhes_ordem_servico.html",
        logo_url=logo_url,
        codigo_orcamento=orcamento_salvo.codigo,
        data_salvo=orcamento_salvo.data_salvo,
        cliente_nome=orcamentos[0].cliente.nome if orcamentos else "Desconhecido",
        orcamentos=orcamentos,
        materiais_agrupados=materiais_agrupados,
        grupos_pecas_json=grupos_pecas_json,
        telefone_usuario=telefone_usuario,
        desenho_salvo=desenho_salvo
    )

@app.route('/excluir_item_orcamento/<codigo>', methods=['POST'])
def excluir_item_orcamento(codigo):
    try:
        # Verificar se o usuário está logado
        if 'user_cpf' not in session:
            flash("Você precisa fazer login para realizar esta ação.", "error")
            return redirect(url_for('login'))
        
        # Obter dados do formulário
        item_id = request.form.get('item_id')
        ambiente_nome = request.form.get('ambiente')
        descricao_nome = request.form.get('descricao')
        tipo_produto = request.form.get('tipo_produto')
        
        if not item_id:
            flash("ID do item não fornecido!", "error")
            return redirect(url_for('detalhes_orcamento_salvo', codigo=codigo))
        
        # Buscar o orçamento salvo
        orcamento_salvo = OrcamentoSalvo.query.filter_by(codigo=codigo).first()
        
        if not orcamento_salvo:
            flash("Orçamento salvo não encontrado!", "error")
            return redirect(url_for('listar_orcamentos_salvos'))
        
        # Verificar permissões
        usuario = Usuario.query.filter_by(cpf=session.get('user_cpf')).first()
        if not session.get('admin') and orcamento_salvo.criado_por != usuario.nome:
            flash("Você não tem permissão para excluir itens deste orçamento!", "error")
            return redirect(url_for('detalhes_orcamento_salvo', codigo=codigo))
        
        # Verificar se o item existe (mas NÃO vamos excluí-lo fisicamente)
        orcamento_item = Orcamento.query.get(int(item_id))
        
        if not orcamento_item:
            flash("Item não encontrado!", "error")
            return redirect(url_for('detalhes_orcamento_salvo', codigo=codigo))
        
        # Verificar se o item pertence a este orçamento salvo
        orcamento_ids = orcamento_salvo.orcamentos_ids.split(',')
        
        if str(item_id) not in orcamento_ids:
            flash("Este item não pertence a este orçamento!", "error")
            return redirect(url_for('detalhes_orcamento_salvo', codigo=codigo))
        
        # 🔥 REGISTRAR REMOÇÃO antes de remover da lista
        # Verificar se já existe registro para este item
        remocao_existente = ItemRemovidoOrcamento.query.filter_by(
            orcamento_salvo_codigo=codigo,
            item_id=item_id
        ).first()
        
        if not remocao_existente:
            # Criar novo registro de remoção
            nova_remocao = ItemRemovidoOrcamento(
                orcamento_salvo_codigo=codigo,
                item_id=item_id,
                cliente_id=orcamento_item.cliente_id
            )
            db.session.add(nova_remocao)
        
        # Remover o ID do item excluído da lista de IDs
        orcamento_ids_atualizados = [id.strip() for id in orcamento_ids if id.strip() != str(item_id)]
        
        # Verificar se ainda há itens no orçamento salvo
        if not orcamento_ids_atualizados:
            # Se não houver mais itens, excluir o orçamento salvo
            db.session.delete(orcamento_salvo)
            db.session.commit()
            
            flash("Todos os itens foram removidos. O orçamento salvo foi excluído.", "success")
            return redirect(url_for('listar_orcamentos_salvos'))
        
        # Atualizar a lista de IDs no orçamento salvo
        orcamento_salvo.orcamentos_ids = ','.join(orcamento_ids_atualizados)
        
        # Recalcular o valor total do orçamento salvo
        orcamentos_restantes = Orcamento.query.filter(
            Orcamento.id.in_([int(id) for id in orcamento_ids_atualizados if id.isdigit()])
        ).all()
        
        novo_valor_total = sum(orc.valor_total for orc in orcamentos_restantes)
        orcamento_salvo.valor_total = novo_valor_total
        
        db.session.commit()
        
        # 🔥 Log da operação
        print(f"✅ Item removido da lista (não excluído do BD): ID={item_id}, Tipo={tipo_produto}")
        print(f"ðŸ’° Valor total atualizado: R$ {novo_valor_total:.2f}")
        print(f"ðŸ“‹ IDs restantes: {orcamento_ids_atualizados}")
        
        # ðŸ”¥ Redirecionar com mensagem de sucesso
        flash("Item removido do orçamento salvo com sucesso!", "success")
        return redirect(url_for('detalhes_orcamento_salvo', codigo=codigo, item_excluido='true'))
    
    except Exception as e:
        db.session.rollback()
        print(f"âŒ Erro ao remover item: {str(e)}")
        import traceback
        traceback.print_exc()
        
        flash(f"Erro ao remover item: {str(e)}", "error")
        return redirect(url_for('detalhes_orcamento_salvo', codigo=codigo, erro='true'))

@app.route('/restaurar_item_orcamento/<codigo>/<int:item_id>', methods=['POST'])
def restaurar_item_orcamento(codigo, item_id):
    """Rota para restaurar um item que foi removido do orçamento salvo"""
    try:
        if 'user_cpf' not in session:
            return jsonify({"success": False, "error": "Não autenticado"}), 401
        
        orcamento_salvo = OrcamentoSalvo.query.filter_by(codigo=codigo).first()
        if not orcamento_salvo:
            return jsonify({"success": False, "error": "Orçamento não encontrado"}), 404
        
        # Verificar se o item existe
        orcamento_item = Orcamento.query.get(item_id)
        if not orcamento_item:
            return jsonify({"success": False, "error": "Item não encontrado"}), 404
        
        # Verificar se o item já está na lista
        orcamento_ids = orcamento_salvo.orcamentos_ids.split(',')
        if str(item_id) in [id.strip() for id in orcamento_ids]:
            return jsonify({"success": False, "error": "Item já está no orçamento"}), 400
        
        # Adicionar o item de volta à lista
        orcamento_ids.append(str(item_id))
        orcamento_salvo.orcamentos_ids = ','.join(orcamento_ids)
        
        # 🔥 REMOVER REGISTRO DE REMOÇÃO
        ItemRemovidoOrcamento.query.filter_by(
            orcamento_salvo_codigo=codigo,
            item_id=item_id
        ).delete()
        
        # Recalcular valor total
        orcamentos = Orcamento.query.filter(
            Orcamento.id.in_([int(id) for id in orcamento_ids if id.strip().isdigit()])
        ).all()
        
        novo_valor_total = sum(orc.valor_total for orc in orcamentos)
        orcamento_salvo.valor_total = novo_valor_total
        
        db.session.commit()
        
        return jsonify({
            "success": True,
            "message": "Item restaurado com sucesso",
            "novo_valor_total": novo_valor_total
        })
    
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/itens_excluidos_orcamento/<codigo>')
def itens_excluidos_orcamento(codigo):
    """Página para ver itens que foram removidos do orçamento salvo"""
    if 'user_cpf' not in session:
        return redirect(url_for('login'))
    
    orcamento_salvo = OrcamentoSalvo.query.filter_by(codigo=codigo).first()
    if not orcamento_salvo:
        flash("Orçamento não encontrado", "error")
        return redirect(url_for('listar_orcamentos_salvos'))
    
    # IDs atuais no orçamento salvo
    ids_atuais = [int(id.strip()) for id in orcamento_salvo.orcamentos_ids.split(',') if id.strip().isdigit()]
    
    # Buscar todos os orçamentos do cliente (para sugerir itens para restaurar)
    primeiro_id = ids_atuais[0] if ids_atuais else None
    if primeiro_id:
        primeiro_orcamento = Orcamento.query.get(primeiro_id)
        if primeiro_orcamento:
            cliente_id = primeiro_orcamento.cliente_id
            
            # Todos os orçamentos deste cliente
            todos_orcamentos_cliente = Orcamento.query.filter_by(cliente_id=cliente_id).all()
            
            # Filtrar apenas os que NÃO estão no orçamento salvo
            itens_disponiveis = [
                orc for orc in todos_orcamentos_cliente 
                if orc.id not in ids_atuais
            ]
        else:
            itens_disponiveis = []
    else:
        itens_disponiveis = []
    
    return render_template(
        'itens_excluidos_orcamento.html',
        codigo=codigo,
        itens_disponiveis=itens_disponiveis,
        total_itens=len(itens_disponiveis)
    )

@app.route('/api/itens_excluidos_modal/<codigo>')
def itens_excluidos_modal(codigo):
    """API para carregar itens EXCLUÍDOS (removidos) deste orçamento específico"""
    try:
        if 'user_cpf' not in session:
            return jsonify({"success": False, "error": "Não autenticado"}), 401
        
        orcamento_salvo = OrcamentoSalvo.query.filter_by(codigo=codigo).first()
        if not orcamento_salvo:
            return jsonify({"success": False, "error": "Orçamento não encontrado"}), 404
        
        # Buscar itens registrados como removidos deste orçamento
        remocoes = ItemRemovidoOrcamento.query.filter_by(
            orcamento_salvo_codigo=codigo
        ).all()
        
        itens_removidos = []
        
        for remocao in remocoes:
            orcamento = Orcamento.query.get(remocao.item_id)
            
            if orcamento:  # Se o item ainda existe no sistema
                itens_removidos.append({
                    'id': orcamento.id,
                    'tipo_produto': orcamento.tipo_produto,
                    'produto_nome': orcamento.produto.nome if orcamento.produto else None,
                    'material_nome': orcamento.material.nome if orcamento.material else '',
                    'comprimento': orcamento.comprimento,
                    'largura': orcamento.largura,
                    'quantidade': orcamento.quantidade,
                    'valor_total': orcamento.valor_total,
                    'cliente_nome': orcamento.cliente.nome if orcamento.cliente else '',
                    'ambiente_nome': orcamento.ambiente.nome if orcamento.ambiente else None,
                    'descricao_nome': orcamento.descricao.nome if orcamento.descricao else None,
                    'data_remocao': remocao.data_remocao.strftime('%d/%m/%Y %H:%M') if remocao.data_remocao else ''
                })
        
        return jsonify({"success": True, "itens": itens_removidos})
    
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/itens_excluidos_count/<codigo>')
def itens_excluidos_count(codigo):
    """API para contar quantos itens foram removidos deste orçamento"""
    try:
        if 'user_cpf' not in session:
            return jsonify({"success": False, "error": "Não autenticado"}), 401
        
        # Contar itens removidos deste orçamento
        count = db.session.query(db.func.count(ItemRemovidoOrcamento.id)).filter_by(
            orcamento_salvo_codigo=codigo
        ).scalar() or 0
        
        return jsonify({"success": True, "count": count})
    
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500



criar_banco()

if __name__ == '__main__':
    port = int(os.getenv("PORT", "5000"))
    host = os.getenv("HOST", "127.0.0.1")
    debug = os.getenv("FLASK_DEBUG", "1").lower() in ("1", "true", "yes", "on")
    open_browser = os.getenv("OPEN_BROWSER", "1").lower() in ("1", "true", "yes", "on")

    if open_browser and host in ("127.0.0.1", "localhost") and (not debug or os.getenv("WERKZEUG_RUN_MAIN") == "true"):
        import threading
        import webbrowser

        threading.Timer(1.2, lambda: webbrowser.open(f"http://127.0.0.1:{port}")).start()

    app.run(host=host, port=port, debug=debug)
