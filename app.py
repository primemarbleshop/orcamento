# 📌 Imports de Bibliotecas Externas
from flask import Flask, render_template, make_response, request, redirect, url_for, jsonify, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from pytz import timezone
from weasyprint import HTML
import io
import fitz  # PyMuPDF
import requests
import base64
import os

from models import db, Orcamento, OrcamentoSalvo, Usuario  # Modelos do SQLAlchemy

# 📌 Importa Configuração Externa
from config import Config

# 📌 Inicializa o Flask
app = Flask(__name__)
app.config.from_object(Config)  # Aplica configurações do config.py

# 📌 Inicializa o Banco de Dados
db = SQLAlchemy(app)
migrate = Migrate(app, db)

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

br_tz = timezone('America/Sao_Paulo')

class Usuario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    cpf = db.Column(db.String(14), unique=True, nullable=False)
    telefone = db.Column(db.String(20), nullable=True)
    senha = db.Column(db.String(200), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)

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

class Ambiente(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    dono = db.Column(db.String(14), nullable=False)
    
    __table_args__ = (db.UniqueConstraint('nome', 'dono', name='_ambiente_nome_dono_uc'),)

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
    prazo_entrega = db.Column(db.Integer, default=15, nullable=False)
    desconto_avista = db.Column(db.Integer, default=5, nullable=False)
    desconto_parcelado = db.Column(db.Integer, default=10, nullable=False)
    observacoes = db.Column(db.Text, default="Medidas sujeitas a confirmação no local. Valores válidos por 7 dias.", nullable=False)
    exclude_payments = db.Column(db.String(50), default='')

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
        ultimo = db.session.query(db.func.max(OrcamentoSalvo.id)).scalar()
        if not ultimo:
            novo_id = 100
        else:
            novo_id = ultimo + 1

        self.codigo = f"O{novo_id:06d}"

class Orcamento(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('cliente.id'))
    cliente = db.relationship('Cliente', backref=db.backref('orcamentos', lazy=True))
    ambiente_id = db.Column(db.Integer, db.ForeignKey('ambiente.id'))
    ambiente = db.relationship('Ambiente', backref=db.backref('orcamentos', lazy=True))
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
    profundidade_nicho = db.Column(db.Float, default=0.0)
    tem_fundo = db.Column(db.String(50), default="Sim")
    tem_alisar = db.Column(db.String(50), default="Não")
    largura_alisar = db.Column(db.Float, default=0.0)

# Função para inicializar o banco de dados
def criar_banco():
    with app.app_context():
        db.create_all()

@app.route('/')
def index():
    if 'user_cpf' not in session:
        return redirect(url_for('login'))
    
    return render_template('index.html')

@app.route('/orcamentos', methods=['GET', 'POST'])
def listar_orcamentos():
    selected_cliente_id = None
    selected_material_id = None
    selected_ambiente_id = None

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
        tipo_produto = request.form['tipo_produto']
        material_id = request.form['material_id']
        quantidade = int(request.form['quantidade'])
        comprimento = float(request.form.get('comprimento', 0) or 0)
        largura = float(request.form.get('largura', 0) or 0)
        instalacao = request.form.get('instalacao', 'Não')  # padrão = "Não"
        instalacao_valor = float(request.form.get('instalacao_valor', 0) or 0)
        rt = request.form.get('rt', 'Não')
        rt_percentual = float(request.form.get('rt_percentual', 0) or 0)
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
        tem_cooktop = request.form.get('tem_cooktop', 'Não')
        profundidade_nicho = float(request.form.get('profundidade_nicho', 0) or 0)
        tem_fundo = request.form.get('tem_fundo', 'Não')
        tem_alisar = request.form.get('tem_alisar', 'Não')
        largura_alisar = float(request.form.get('largura_alisar', 0) or 0)
        data=data_atual

        tem_alisar = request.form.get('alisar', 'Não')
        largura_alisar = float(request.form.get('largura_alisar', 0) or 0)

        tipo_cuba = request.form.get('tipo_cuba', '')
        quantidade_cubas = int(request.form.get('quantidade_cubas', 0)) if tipo_cuba else 0

        tem_cooktop = request.form.get('tem_cooktop', 'Não')

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

        cooktop_valor = 50

        material = Material.query.get(material_id)
        valor_total = 0
        valor_total_criar = 0

        comprimento_cal = max(comprimento, 10)
        largura_cal = max(largura, 10)
        valor_base = material.valor * (comprimento_cal * largura_cal / 10000)

        if tipo_produto in ['Bancada', 'Lavatorio']:
            if material.valor < 1000:
                valor_base *= 1.3
            elif material.valor < 2000:
                valor_base *= 1.15
            elif material.valor < 1000000:
                valor_base *= 1.1

        if tipo_produto == 'Ilharga Bipolida' and valor_base < 1000000:
            valor_base *= 1.15

        valor_total_criar += valor_base

        if tipo_produto == 'Nicho':
            comprimento_cal = 10 if 0 < comprimento < 10 else comprimento
            largura_cal = 10 if 0 < largura < 10 else largura
            profundidade_nicho_cal = 10 if 0 < profundidade_nicho < 10 else profundidade_nicho
            
            if tem_fundo == 'Sim':
                area_nicho = ((comprimento_cal) * (largura_cal)) + (((comprimento_cal) * profundidade_nicho_cal) * 2) + ((largura_cal * profundidade_nicho_cal) * 2)
            else:
                area_nicho = ((comprimento_cal) + (largura_cal)) * profundidade_nicho_cal * 2

            if tem_alisar == 'Sim' and largura_alisar > 0:
                largura_alisar_cal = 10 if 0 < largura_alisar < 10 else largura_alisar
                area_nicho += ((comprimento_cal + (largura_alisar_cal * 2)) * largura_alisar_cal * 2) + \
                              ((largura_cal + (largura_alisar_cal * 2)) * largura_alisar_cal * 2)

            valor_nicho = ((area_nicho / 10000) * material.valor) + 150
            valor_total_criar = valor_nicho
                                       
        if tipo_produto in ['Ilharga', 'Ilharga Bipolida', 'Bancada', 'Lavatorio']:
            comprimento_saia_cal = 10 if 0 < comprimento_saia < 10 else comprimento_saia
            largura_saia_cal = 10 if 0 < largura_saia < 10 else largura_saia
            valor_saia = comprimento_saia_cal * largura_saia_cal * material.valor / 10000
            valor_total_criar += valor_saia

        if tipo_produto in ['Bancada', 'Lavatorio']:
            comprimento_fronte_cal = 10 if 0 < comprimento_fronte < 10 else comprimento_fronte
            largura_fronte_cal = 10 if 0 < largura_fronte < 10 else largura_fronte
            valor_fronte = comprimento_fronte_cal * largura_fronte_cal * material.valor / 10000
            valor_total_criar += valor_fronte

        if tipo_produto == 'Pedra de Box':
            valor_pedra_box = (valor_base) + 30
            valor_total_criar += valor_pedra_box

        if tipo_cuba:
            valor_cuba = cuba_valores.get(tipo_cuba, 0)
            valor_total_criar += valor_cuba * quantidade_cubas

            if tipo_cuba == 'Esculpida':
                modelo_cuba = request.form.get('modelo_cuba', 'Normal')
                comprimento_cuba = float(request.form.get('comprimento_cuba', 0))
                largura_cuba = float(request.form.get('largura_cuba', 0))
                profundidade_cuba = float(request.form.get('profundidade_cuba', 0))
            
                if modelo_cuba == 'Prainha':
                    m2_cuba = ((comprimento_cuba * largura_cuba) + (largura_cuba * 2) * profundidade_cuba) / 10000
                else:
                    m2_cuba = ((comprimento_cuba * largura_cuba * 2) +
                               (comprimento_cuba * 2 + largura_cuba * 2) * profundidade_cuba) / 10000

                valor_cuba_esculpida = m2_cuba * material.valor * quantidade_cubas
                valor_total_criar += valor_cuba_esculpida

        if tem_cooktop == 'Sim':
            valor_total_criar += cooktop_valor

        if instalacao == 'Sim':
            valor_total_criar += instalacao_valor

        valor_total_criar *= quantidade

        valor_rt = 0.0
        if rt == 'Sim' and rt_percentual > 0:
            valor_rt = valor_total_criar / (1 - rt_percentual / 100) - valor_total_criar

        valor_total = round(valor_total_criar + valor_rt, 2)

        modelo_cuba = request.form.get("modelo_cuba", "").strip()
        if not modelo_cuba:  
            modelo_cuba = "Normal"

        if cliente_id and material_id and ambiente_id:
            novo_orcamento = Orcamento(
                cliente_id=cliente_id,
                ambiente_id=ambiente_id,
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
    else:
        clientes = Cliente.query.filter_by(dono=user_cpf).order_by(Cliente.nome).all()
        ambientes = Ambiente.query.filter_by(dono=user_cpf).order_by(Ambiente.nome).all()

    materiais = Material.query.order_by(Material.nome).all()
    is_admin = session.get('admin', False)

    return render_template(
        'orcamentos.html',
        orcamentos=orcamentos,
        clientes=clientes,
        ambientes=ambientes,
        materiais=materiais,
        is_admin=is_admin,
        # Passar os filtros atuais para o template
        filtro_cliente_atual=filtro_cliente,
        filtro_data_inicio_atual=filtro_data_inicio,
        filtro_data_fim_atual=filtro_data_fim,
        limite_atual=limite_int
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

@app.route('/clientes/edit/<int:id>', methods=['GET', 'POST'])
def editar_cliente(id):
    cliente = Cliente.query.get(id)

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

    return render_template('editar_cliente.html', cliente=cliente)


@app.route('/materiais/edit/<int:id>', methods=['GET', 'POST'])
def editar_material(id):
    material = Material.query.get(id)
    if request.method == 'POST':
        material.nome = request.form['nome']
        material.valor = float(request.form['valor'])
        db.session.commit()
        return redirect(url_for('materiais'))
    return render_template('editar_material.html', material=material)

@app.route('/orcamentos/edit/<int:id>', methods=['GET', 'POST'])
def editar_orcamento(id):
    orcamento = Orcamento.query.get_or_404(id)
    if not orcamento:
        flash("Erro: Orçamento não encontrado!", "error")
        return redirect(url_for('listar_orcamentos'))

    # Obtendo CPF do usuário logado
    usuario_cpf = session.get('user_cpf')  

    # Filtrar apenas os clientes cujo dono é o usuário logado
    clientes = Cliente.query.filter_by(dono=usuario_cpf).all()
    ambientes = Ambiente.query.filter_by(dono=usuario_cpf).order_by(Ambiente.nome).all()

    materiais = Material.query.all()

    orcamentos_salvos = (
        db.session.query(OrcamentoSalvo)
        .join(Orcamento, db.func.instr(OrcamentoSalvo.orcamentos_ids, db.cast(Orcamento.id, db.String())) > 0)
        .join(Cliente, Cliente.id == Orcamento.cliente_id)
        .filter(Cliente.dono == usuario_cpf)  # Filtra apenas se o usuário for dono do cliente
        .distinct()
        .all()
    )

    
    
    

    if request.method == 'POST':
        # Atualizando os dados do orçamento com as informações do formulário
        orcamento.cliente_id = request.form.get('cliente_id')
        orcamento.tipo_produto = request.form['tipo_produto']
        orcamento.ambiente_id = request.form.get('ambiente_id')
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
        orcamento.tem_cooktop = request.form.get('tem_cooktop', orcamento.tem_cooktop)
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
        if orcamento.tipo_produto == 'Ilharga Bipolida' and valor_base < 1000000:
            valor_base *= 1.15

        valor_total_criar += valor_base  # Inicializando o valor total

        # **Cálculo do Nicho**
        if orcamento.tipo_produto == 'Nicho':
            orcamento.comprimento_cal = 10 if 0 < orcamento.comprimento < 10 else orcamento.comprimento
            orcamento.largura_cal = 10 if 0 < orcamento.largura < 10 else orcamento.largura
            orcamento.profundidade_nicho_cal = 10 if 0 < orcamento.profundidade_nicho < 10 else orcamento.profundidade_nicho
            if orcamento.tem_fundo == 'Sim':  # Verifica se o nicho tem fundo
                area_nicho = ((orcamento.comprimento_cal) * (orcamento.largura_cal)) + \
                             (((orcamento.comprimento_cal) * orcamento.profundidade_nicho_cal) * 2) + \
                             ((orcamento.largura_cal * orcamento.profundidade_nicho_cal) * 2)
            else:  # Caso o nicho não tenha fundo
                area_nicho = ((orcamento.comprimento_cal) + (orcamento.largura_cal)) * orcamento.profundidade_nicho_cal * 2

            # Verifica se há alisar e ajusta a área do nicho
            if orcamento.tem_alisar == 'Sim' and orcamento.largura_alisar > 0:
                orcamento.largura_alisar_cal = 10 if 0 < orcamento.largura_alisar < 10 else orcamento.largura_alisar
                area_nicho += ((orcamento.comprimento_cal + (orcamento.largura_alisar_cal * 2)) * orcamento.largura_alisar_cal * 2) + \
                              ((orcamento.largura_cal + (orcamento.largura_alisar_cal * 2)) * orcamento.largura_alisar_cal * 2)

            # Calcula o valor do nicho e adiciona ao total
            valor_nicho = (area_nicho / 10000) * material.valor + 150
            valor_total_criar = valor_nicho
                                       
        # **Cálculo do Acabamento Saia**
        if orcamento.tipo_produto in ['Ilharga', 'Ilharga Bipolida', 'Bancada', 'Lavatorio']:
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
            valor_pedra_box = (valor_base) + 30
            valor_total_criar += valor_pedra_box

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
        orcamento.valor_total = round(valor_total_criar + valor_rt, 2)
        
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
        clientes=clientes,
        materiais=materiais,
        orcamentos_salvos=orcamentos_salvos
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
    orcamento = Orcamento.query.get(id)
    if not orcamento:
        flash("Erro: Orçamento não encontrado.", "error")
        return redirect(url_for('listar_orcamentos'))

    # Verifica se esse orçamento pertence a um orçamento salvo
    orcamento_salvo = OrcamentoSalvo.query.filter(OrcamentoSalvo.orcamentos_ids.contains(str(id))).first()

    # Exclui o orçamento individual
    db.session.delete(orcamento)
    db.session.commit()

    # Atualiza o orçamento salvo após a remoção
    if orcamento_salvo:
        atualizar_valor_orcamento_salvo(orcamento_salvo.id)

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

# 🚀 Rota para exibir detalhes dos orçamentos selecionados
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

        # Obter o nome do cliente do primeiro orçamento
        cliente_nome = orcamentos[0].cliente.nome if orcamentos else "Orçamentos"

        valor_total_final = sum(o.valor_total for o in orcamentos)
        valor_total_formatado = "R$ {:,.2f}".format(valor_total_final).replace(",", "X").replace(".", ",").replace("X", ".")

        return render_template(
            'detalhes_orcamento.html',
            orcamentos=orcamentos,
            cliente_nome=cliente_nome,
            valor_total_final=valor_total_formatado
        )

    except Exception as e:
        return f"Erro ao carregar detalhes dos orçamentos: {str(e)}", 500


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        cpf = request.form['cpf']
        senha = request.form['senha']

        # 🔥 CORREÇÃO: Remove pontos e traços do CPF para buscar no banco
        cpf_limpo = re.sub(r'[\.\-]', '', cpf)

        usuario = Usuario.query.filter_by(cpf=cpf_limpo).first()

        if usuario and usuario.check_senha(senha):
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
            novo_usuario = Usuario(nome=nome, cpf=cpf, telefone=telefone, is_admin=False)
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

    usuarios = Usuario.query.filter_by(is_admin=False).all()

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
        db.session.delete(usuario)
        db.session.commit()
        flash("Usuário deletado com sucesso!", "success")
    else:
        flash("Erro: Usuário não encontrado!", "error")

    return redirect(url_for('gerenciar_usuarios'))

from flask import Flask, request, jsonify
from datetime import datetime
import time  # Certifique-se de importar time

@app.route('/salvar_orcamento', methods=['POST'])
def salvar_orcamento():
    try:
        # 🔹 Pegando os dados do JSON enviado pelo frontend
        data = request.json
        ids = data.get('ids')

        if not ids:
            return jsonify({"success": False, "error": "Nenhum orçamento selecionado!"}), 400

        # 🔹 Convertendo a string de IDs para uma lista de inteiros
        ids = [int(id.strip()) for id in ids.split(",") if id.strip().isdigit()]
        if not ids:
            return jsonify({"success": False, "error": "IDs inválidos!"}), 400

        # 🔹 Buscar o usuário pelo CPF salvo na sessão
        usuario = Usuario.query.filter_by(cpf=session.get('user_cpf')).first()
        criado_por = usuario.nome if usuario else "Desconhecido"  # Nome do usuário logado

        # 🔹 Gerar o código sequencial iniciando em O000100
        ultimo_orcamento = db.session.query(db.func.max(OrcamentoSalvo.id)).scalar()
        novo_codigo = f"O{(100 + (ultimo_orcamento or 0)):06d}"

        # 🔹 Data de salvamento
        data_salvamento = datetime.now(br_tz)

        # 🔹 Calcular o valor total dos orçamentos selecionados
        valor_total = db.session.query(db.func.sum(Orcamento.valor_total)).filter(Orcamento.id.in_(ids)).scalar()
        valor_total = valor_total if valor_total else 0.0
        
        # 🔹 Criar o novo orçamento salvo
        novo_orcamento = OrcamentoSalvo(
            codigo=novo_codigo,
            data_salvo=data_salvamento,
            orcamentos_ids=",".join(map(str, ids)),  # IDs dos orçamentos vinculados
            valor_total=valor_total,
            criado_por=criado_por  # 🔹 Agora pega o nome diretamente do banco de dados
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
    orcamento_salvo = OrcamentoSalvo.query.filter_by(codigo=codigo).first()

    if not orcamento_salvo:
        flash("Orçamento salvo não encontrado!", "danger")
        return redirect(url_for('listar_orcamentos_salvos'))

    ids = [int(id) for id in orcamento_salvo.orcamentos_ids.split(",")]
    orcamentos = Orcamento.query.filter(Orcamento.id.in_(ids)).all()
    
    # Agrupar orçamentos por ambiente
    ambientes_agrupados = {}
    for orcamento in orcamentos:
        ambiente_nome = orcamento.ambiente.nome if orcamento.ambiente else 'Sem Ambiente'
        if ambiente_nome not in ambientes_agrupados:
            ambientes_agrupados[ambiente_nome] = {}
        
        tipo_produto = orcamento.tipo_produto
        if tipo_produto not in ambientes_agrupados[ambiente_nome]:
            ambientes_agrupados[ambiente_nome][tipo_produto] = []
        
        ambientes_agrupados[ambiente_nome][tipo_produto].append(orcamento)

    valor_total_final = sum(o.valor_total for o in orcamentos)
    valor_total_float = valor_total_final

    logo_url = "https://orcamento-t9w2.onrender.com/static/logo.jpg"
    
    usuario = Usuario.query.filter_by(cpf=session.get('user_cpf')).first()
    telefone_usuario = usuario.telefone if usuario else ""

    prazo_entrega = orcamento_salvo.prazo_entrega if orcamento_salvo.prazo_entrega is not None else 15
    desconto_avista = orcamento_salvo.desconto_avista if orcamento_salvo.desconto_avista is not None else 5
    desconto_parcelado = orcamento_salvo.desconto_parcelado if orcamento_salvo.desconto_parcelado is not None else 10
    observacoes = orcamento_salvo.observacoes if orcamento_salvo.observacoes is not None else "Medidas sujeitas a confirmação no local. Valores válidos por 7 dias."
    
    exclude_payments = orcamento_salvo.exclude_payments.split(',') if orcamento_salvo.exclude_payments else []

    return render_template(
        "detalhes_orcamento_salvo.html",
        logo_url=logo_url,
        codigo_orcamento=orcamento_salvo.codigo,
        data_salvo=orcamento_salvo.data_salvo,
        cliente_nome=orcamentos[0].cliente.nome if orcamentos else "Desconhecido",
        orcamentos=orcamentos,
        ambientes_agrupados=ambientes_agrupados,  # Nova variável para agrupamento
        valor_total_final="R$ {:,.2f}".format(valor_total_final).replace(",", "X").replace(".", ",").replace("X", "."),
        valor_total_float=valor_total_float,
        telefone_usuario=telefone_usuario,
        prazo_entrega=prazo_entrega,
        desconto_avista=desconto_avista,
        desconto_parcelado=desconto_parcelado,
        observacoes=observacoes,
        exclude_payments=exclude_payments
    )


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

        db.session.delete(orcamento)
        db.session.commit()
        
        return jsonify({"success": "Orçamento deletado com sucesso!"})
    
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Erro ao excluir orçamento: {str(e)}"}), 500

@app.route('/atualizar_status_tipo_cliente', methods=['POST'])
def atualizar_status_tipo_cliente():
    try:
        data = request.json
        orcamento_id = data.get('id')
        novo_status = data.get('status')
        novo_tipo_cliente = data.get('tipo_cliente')

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

        db.session.commit()

        return jsonify({"success": True, "message": "Orçamento atualizado com sucesso!"})

    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
        



@app.route('/gerar_pdf_orcamento/<codigo>')
def gerar_pdf_orcamento(codigo):
    orcamento_salvo = OrcamentoSalvo.query.filter_by(codigo=codigo).first()
    if not orcamento_salvo:
        flash("Orçamento salvo não encontrado!", "danger")
        return redirect(url_for('listar_orcamentos_salvos'))

    ids = [int(id) for id in orcamento_salvo.orcamentos_ids.split(",")]
    orcamentos = Orcamento.query.filter(Orcamento.id.in_(ids)).all()
    
    # Agrupar orçamentos por ambiente (igual ao detalhes_orcamento_salvo)
    ambientes_agrupados = {}
    for orcamento in orcamentos:
        ambiente_nome = orcamento.ambiente.nome if orcamento.ambiente else 'Sem Ambiente'
        if ambiente_nome not in ambientes_agrupados:
            ambientes_agrupados[ambiente_nome] = {}
        
        tipo_produto = orcamento.tipo_produto
        if tipo_produto not in ambientes_agrupados[ambiente_nome]:
            ambientes_agrupados[ambiente_nome][tipo_produto] = []
        
        ambientes_agrupados[ambiente_nome][tipo_produto].append(orcamento)
    
    # Calcular valor total
    valor_total_final = sum(o.valor_total for o in orcamentos)
    valor_total_float = valor_total_final

    # Definir logo_url (esta linha estava faltando)
    logo_url = "https://orcamento-t9w2.onrender.com/static/logo.jpg"
    
    # Obter informações do usuário
    usuario = Usuario.query.filter_by(cpf=session.get('user_cpf')).first()
    telefone_usuario = usuario.telefone if usuario else ""

    # ✅ USAR OS VALORES SALVOS NO BANCO COM VALORES PADRÃO DE FALLBACK
    prazo_entrega = orcamento_salvo.prazo_entrega if orcamento_salvo.prazo_entrega is not None else 15
    desconto_avista = orcamento_salvo.desconto_avista if orcamento_salvo.desconto_avista is not None else 5
    desconto_parcelado = orcamento_salvo.desconto_parcelado if orcamento_salvo.desconto_parcelado is not None else 10
    observacoes = orcamento_salvo.observacoes if orcamento_salvo.observacoes is not None else "Medidas sujeitas a confirmação no local. Valores válidos por 7 dias."
    
    # ✅ NOVO: Obter as opções excluídas salvas no banco
    exclude_payments = orcamento_salvo.exclude_payments.split(',') if orcamento_salvo.exclude_payments else []

    # Renderizar o HTML para o PDF
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
        prazo_entrega=prazo_entrega,
        desconto_avista=desconto_avista,
        desconto_parcelado=desconto_parcelado,
        observacoes=observacoes,
        pdf=True,
        exclude_payments=exclude_payments
    )

    # Resto do código permanece igual...
    temp_pdf_path = "/tmp/temp_orcamento.pdf"
    HTML(string=rendered_html, base_url="https://orcamento-t9w2.onrender.com").write_pdf(temp_pdf_path)

    logo_path = "static/logo.jpg"
    final_pdf_path = "/tmp/final_orcamento.pdf"
    doc = fitz.open(temp_pdf_path)

    if os.path.exists(logo_path):
        page = doc[0]
        page_width = page.rect.width
        page_height = page.rect.height

        logo_width = 240
        logo_height = 120

        rect = fitz.Rect(page_width - logo_width - -20, 20, page_width - -20, 20 + logo_height)
        page.insert_image(rect, filename=logo_path)

    doc.save(final_pdf_path)
    doc.close()

    with open(final_pdf_path, "rb") as pdf_file:
        pdf_bytes = pdf_file.read()

    response = make_response(pdf_bytes)
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = f"inline; filename=orcamento_{codigo}.pdf"

    os.remove(temp_pdf_path)
    os.remove(final_pdf_path)

    return response


@app.route('/orcamentos/editar_material_rt_selecionados', methods=['POST'])
def editar_material_rt_selecionados():
    data = request.get_json()
    orcamento_ids = data.get('orcamento_ids', [])
    material_id = data.get('material_id')  # Pode ser None
    rt = data.get('rt')  # Pode ser None (manter atual)
    rt_percentual = data.get('rt_percentual', 0.0)

    if not orcamento_ids:
        return jsonify({'erro': 'Nenhum orçamento selecionado.'}), 400

    # Se material_id foi fornecido, validar se existe
    if material_id:
        material = Material.query.get(material_id)
        if not material:
            return jsonify({'erro': 'Material não encontrado.'}), 404
    else:
        material = None

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
        # Atualizar material apenas se foi fornecido
        if material_id:
            orcamento.material_id = material_id
            material_para_calculo = material
        else:
            material_para_calculo = orcamento.material
        
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

        if orcamento.tipo_produto == 'Ilharga Bipolida' and material_para_calculo.valor < 1000000:
            valor_base *= 1.15

        valor_total_criar += valor_base

        # Nicho
        if orcamento.tipo_produto == 'Nicho':
            profundidade_nicho = max(orcamento.profundidade_nicho or 0, 10)
            if orcamento.tem_fundo == 'Sim':
                area_nicho = (comprimento_cal * largura_cal) + (2 * comprimento_cal * profundidade_nicho) + (2 * largura_cal * profundidade_nicho)
            else:
                area_nicho = 2 * (comprimento_cal + largura_cal) * profundidade_nicho

            if orcamento.tem_alisar == 'Sim' and (orcamento.largura_alisar or 0) > 0:
                largura_alisar_cal = 10 if 0 < orcamento.largura_alisar < 10 else orcamento.largura_alisar
                area_nicho += ((comprimento_cal + (largura_alisar_cal * 2)) * largura_alisar_cal * 2) + \
                              ((largura_cal + (largura_alisar_cal * 2)) * largura_alisar_cal * 2)

            valor_nicho = (area_nicho / 10000) * material_para_calculo.valor + 150
            valor_total_criar = valor_nicho

        # Saia
        if orcamento.tipo_produto in ['Ilharga', 'Ilharga Bipolida', 'Bancada', 'Lavatorio']:
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
            valor_pedra_box = valor_base + 30
            valor_total_criar += valor_pedra_box

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

        orcamento.valor_total = round(valor_total_final, 2)

    db.session.commit()

    # 🔥 Atualizar todos os orçamentos salvos afetados
    orcamentos_salvos = OrcamentoSalvo.query.filter(
        db.or_(*[OrcamentoSalvo.orcamentos_ids.like(f"%{id}%") for id in orcamento_ids])
    ).all()

    for orcamento_salvo in orcamentos_salvos:
        atualizar_valor_orcamento_salvo(orcamento_salvo.id)

    return jsonify({'success': 'Materiais e RT atualizados, valores recalculados e orçamentos salvos atualizados.'})


@app.route('/orcamentos/duplicar_selecionados', methods=['POST'])
def duplicar_selecionados():
    data = request.get_json()
    orcamento_ids = data.get('orcamento_ids', [])

    if not orcamento_ids:
        return jsonify({'success': False, 'error': 'Nenhum orçamento selecionado.'}), 400

    try:
        for id in orcamento_ids:
            original = Orcamento.query.get(id)
            if original:
                novo_orcamento = Orcamento(
                    cliente_id = original.cliente_id,
                    ambiente_id = original.ambiente_id,
                    tipo_produto = original.tipo_produto,
                    material_id = original.material_id,
                    quantidade = original.quantidade,
                    comprimento = original.comprimento,
                    largura = original.largura,
                    instalacao = original.instalacao or "Não",
                    instalacao_valor = original.instalacao_valor or 0,
                    rt = original.rt,
                    rt_percentual = original.rt_percentual,
                    comprimento_saia = original.comprimento_saia,
                    largura_saia = original.largura_saia,
                    comprimento_fronte = original.comprimento_fronte,
                    largura_fronte = original.largura_fronte,
                    tipo_cuba = original.tipo_cuba,
                    quantidade_cubas = original.quantidade_cubas,
                    modelo_cuba = original.modelo_cuba,
                    comprimento_cuba = original.comprimento_cuba,
                    largura_cuba = original.largura_cuba,
                    profundidade_cuba = original.profundidade_cuba,
                    tem_cooktop = original.tem_cooktop,
                    profundidade_nicho = original.profundidade_nicho,
                    tem_fundo = original.tem_fundo,
                    tem_alisar = original.tem_alisar,
                    largura_alisar = original.largura_alisar,
                    valor_total = original.valor_total,
                    dono = original.dono,  # <<<< NOVO, ESSENCIAL
                    data = datetime.now(br_tz)
                )

                db.session.add(novo_orcamento)

        db.session.commit()
        return jsonify({'success': True})

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({'success': False, 'error': traceback.format_exc()}), 500

@app.route('/salvar_rodape_orcamento/<codigo>', methods=['POST'])
def salvar_rodape_orcamento(codigo):
    orcamento_salvo = OrcamentoSalvo.query.filter_by(codigo=codigo).first()
    
    if not orcamento_salvo:
        flash("Orçamento salvo não encontrado!", "danger")
        return redirect(url_for('listar_orcamentos_salvos'))
    
    # Atualizar os valores do rodapé
    orcamento_salvo.prazo_entrega = int(request.form.get('prazo_entrega', 15))
    orcamento_salvo.desconto_avista = float(request.form.get('desconto_avista', 5))
    orcamento_salvo.desconto_parcelado = float(request.form.get('desconto_parcelado', 10))
    orcamento_salvo.observacoes = request.form.get('observacoes', '')
    
    # ✅ NOVO: Salvar as opções de pagamento excluídas
    exclude_payments = request.form.get('exclude_payments', '')
    # Armazenar no banco de dados (você precisa adicionar este campo no modelo)
    orcamento_salvo.exclude_payments = exclude_payments
    
    db.session.commit()
    flash("Rodapé do orçamento salvo com sucesso!", "success")
    
    return redirect(url_for('detalhes_orcamento_salvo', codigo=codigo))


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



if __name__ == '__main__':
    criar_banco()
    app.run(debug=True)
