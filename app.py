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

# Definição das tabelas diretamente no app.py
class Usuario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    cpf = db.Column(db.String(14), unique=True, nullable=False)
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
    telefone = db.Column(db.String(50), nullable=True)  # Pode ser vazio
    documento = db.Column(db.String(50), nullable=True)  # Pode ser vazio
    dono = db.Column(db.String(14), nullable=False)  # CPF do usuário que cadastrou

    # Remove a restrição UNIQUE do telefone e do CPF
    __table_args__ = ()  # Remove todas as restrições personalizadas
    
class Material(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    valor = db.Column(db.Float, nullable=False)  # Mantido apenas uma vez

class OrcamentoSalvo(db.Model):
    __tablename__ = "orcamento_salvo"
    
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(20), unique=True, nullable=False)
    data_salvo = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    valor_total = db.Column(db.Float, nullable=False)
    criado_por = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(50), nullable=False, default="Em Espera")  
    tipo_cliente = db.Column(db.String(50), nullable=False, default="Selecionar")
    orcamentos_ids = db.Column(db.String, nullable=False)  # Armazena os IDs separados por vírgula

    @property
    def cliente_nome(self):
        if not self.orcamentos_ids:  # Se não houver IDs, retorna "Não definido"
            return "Não definido"

        primeiro_orcamento_id = self.orcamentos_ids.split(",")[0].strip()  # Remove espaços extras

        if not primeiro_orcamento_id.isdigit():  # Verifica se é um número
            return "Não definido"

        primeiro_orcamento = Orcamento.query.get(int(primeiro_orcamento_id))
        return primeiro_orcamento.cliente.nome if primeiro_orcamento else "Não definido"

    def gerar_codigo(self):
        """ Gera um código único sequencial para o orçamento salvo """
        ultimo = db.session.query(db.func.max(OrcamentoSalvo.id)).scalar()  # Pega o último ID salvo
        if not ultimo:
            novo_id = 100  # Se não houver registros, começa do 100
        else:
            novo_id = ultimo + 1  # Incrementa o último ID encontrado

        self.codigo = f"O{novo_id:06d}"  # Formato: O000100, O000101, O000102, etc.


    

class Orcamento(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('cliente.id'))
    cliente = db.relationship('Cliente', backref=db.backref('orcamentos', lazy=True))
    tipo_produto = db.Column(db.String(100), nullable=False)
    material_id = db.Column(db.Integer, db.ForeignKey('material.id'))
    material = db.relationship('Material', backref=db.backref('orcamentos', lazy=True))
    quantidade = db.Column(db.Integer, nullable=False)
    comprimento = db.Column(db.Float, nullable=False)
    largura = db.Column(db.Float, nullable=False)
    outros_custos = db.Column(db.Float, default=0.0)
    rt = db.Column(db.String(50), default="Não")
    rt_percentual = db.Column(db.Float, default=0.0)
    valor_total = db.Column(db.Float, nullable=False, default=0.0)
    dono = db.Column(db.String(14), nullable=False)  # CPF do usuário que cadastrou

    # Ajuste de fuso horário na data
    data = db.Column(db.DateTime, default=lambda: datetime.now(br_tz))
    
    

    # **Novos Campos para Dados Dinâmicos**
    comprimento_saia = db.Column(db.Float, default=0.0)
    largura_saia = db.Column(db.Float, default=0.0)
    comprimento_fronte = db.Column(db.Float, default=0.0)
    largura_fronte = db.Column(db.Float, default=0.0)

    # **Campos para Cuba**
    tipo_cuba = db.Column(db.String(100), default="")
    quantidade_cubas = db.Column(db.Integer, default=0)
    comprimento_cuba = db.Column(db.Float, default=0.0)
    largura_cuba = db.Column(db.Float, default=0.0)
    profundidade_cuba = db.Column(db.Float, default=0.0)
    modelo_cuba = db.Column(db.String(50))

    # **Campos para Cooktop**
    tem_cooktop = db.Column(db.String(50), default="Não")

    # **Campos para Nicho**
    profundidade_nicho = db.Column(db.Float, default=0.0)
    tem_fundo = db.Column(db.String(50), default="Sim")

    # **Campos para Alisar**
    tem_alisar = db.Column(db.String(50), default="Não")
    largura_alisar = db.Column(db.Float, default=0.0)


# Função para inicializar o banco de dados
def criar_banco():
    with app.app_context():
        db.create_all()

@app.route('/')
def index():
    if 'user_cpf' not in session:  # Se não estiver logado, redireciona para o login
        return redirect(url_for('login'))
    
    
    return render_template('index.html')

@app.route('/orcamentos', methods=['GET', 'POST'])
def listar_orcamentos():
    ultimo_cliente_id = None  # Variável para armazenar o ID do cliente mais recente
    selected_cliente_id = None  # Variável para armazenar o cliente selecionado
    selected_material_id = None  # Variável para armazenar o material selecionado

    if request.method == 'POST':
        cliente_id = request.form.get('cliente_id')
        tipo_produto = request.form['tipo_produto']
        material_id = request.form['material_id']
        quantidade = int(request.form['quantidade'])
        comprimento = float(request.form.get('comprimento', 0) or 0)
        largura = float(request.form.get('largura', 0) or 0)
        outros_custos = float(request.form.get('outros_custos', 0) or 0)
        rt = request.form.get('rt', 'Não')
        rt_percentual = float(request.form.get('rt_percentual', 0) or 0)  # Agora numérico, ex.: 10 para 10%
        data_atual = datetime.now(br_tz)
        dono = session['user_cpf']  # Captura o CPF do usuário logado

        

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

        
        # Inicializando variáveis do alisar
        tem_alisar = request.form.get('alisar', 'Não')
        largura_alisar = float(request.form.get('largura_alisar', 0) or 0)

        # Variáveis de cuba
        tipo_cuba = request.form.get('tipo_cuba', '')
        quantidade_cubas = int(request.form.get('quantidade_cubas', 0)) if tipo_cuba else 0

        # Variáveis de cooktop
        tem_cooktop = request.form.get('tem_cooktop', 'Não')

        # Valores fixos das cubas
        cuba_valores = {
            'Embutir': 225,
            'Esculpida': 0,
            'Cuba Tradicional Inox': 225,
            'Apoio Cliente': 125,
            'Embutida Cliente': 125,
            'Gourmet Cliente': 225,
            'Tanque Inox': 500
        }

        cooktop_valor = 50  # Valor fixo para o cooktop

        # Obtendo o valor do material
        material = Material.query.get(material_id)
        valor_total = 0
        valor_total_criar = 0

        
        comprimento_cal = max(comprimento, 10)  # Garante mínimo de 10 cm
        largura_cal = max(largura, 10)  # Garante mínimo de 10 cm
        # Cálculo do valor base do material
        valor_base = material.valor * (comprimento_cal * largura_cal / 10000)

        # Ajuste de preço para Bancada e Lavatorio
        if tipo_produto in ['Bancada', 'Lavatorio']:
            if material.valor < 1000:
                valor_base *= 1.3
            elif material.valor < 2000:
                valor_base *= 1.15
            elif material.valor < 1000000:
                valor_base *= 1.1

        # Ajuste de preço para Ilharga Bipolida
        if tipo_produto == 'Ilharga Bipolida' and valor_base < 1000000:
            valor_base *= 1.15

        valor_total_criar += valor_base  # Inicializando o valor total

        

        # **Cálculo do Nicho**
        if tipo_produto == 'Nicho':
            comprimento_cal = 10 if 0 < comprimento < 10 else comprimento
            largura_cal = 10 if 0 < largura < 10 else largura
            profundidade_nicho_cal = 10 if 0 < profundidade_nicho < 10 else profundidade_nicho
            
            if tem_fundo == 'Sim':  # Verifica se o nicho tem fundo
                area_nicho = ((comprimento_cal) * (largura_cal)) + (((comprimento_cal) * profundidade_nicho_cal) * 2) + ((largura_cal * profundidade_nicho_cal) * 2)
                print(f"Nicho com fundo: Comprimento={comprimento}, Largura={largura}, Profundidade={profundidade_nicho}, Área={area_nicho}")

            else:  # Caso o nicho não tenha fundo
                area_nicho = ((comprimento_cal) + (largura_cal)) * profundidade_nicho_cal * 2
                print(f"Nicho sem fundo: Comprimento={comprimento}, Largura={largura}, Profundidade={profundidade_nicho}, Área={area_nicho}")

            
            # Verifica se há alisar e ajusta a área do nicho
            if tem_alisar == 'Sim' and largura_alisar > 0:
                largura_alisar_cal = 10 if 0 < largura_alisar < 10 else largura_alisar
                area_nicho += ((comprimento_cal + (largura_alisar_cal * 2)) * largura_alisar_cal * 2) + \
                              ((largura_cal + (largura_alisar_cal * 2)) * largura_alisar_cal * 2)
                print(f"Alisar aplicado: Comprimento={comprimento}, Largura={largura}, Largura do Alisar={largura_alisar}, Area nicho={area_nicho}, Área Total={area_nicho}")

            # Calcula o valor do nicho e adiciona ao total
            valor_nicho = ((area_nicho / 10000) * material.valor) + 150
            valor_total_criar = valor_nicho
            print(f"Valor do Nicho: Área Final={area_nicho}, Valor do Material={material.valor}, Valor do Nicho={valor_nicho}, Valor Total Criado={valor_total_criar}")                       

        
        
        # **Cálculo do Acabamento Saia**
        if tipo_produto in ['Ilharga', 'Ilharga Bipolida', 'Bancada', 'Lavatorio']:
            comprimento_saia_cal = 10 if 0 < comprimento_saia < 10 else comprimento_saia
            largura_saia_cal = 10 if 0 < largura_saia < 10 else largura_saia
            valor_saia = comprimento_saia_cal * largura_saia_cal * material.valor / 10000
            valor_total_criar += valor_saia

       

        # **Cálculo do Acabamento Fronte**
        if tipo_produto in ['Bancada', 'Lavatorio']:
            comprimento_fronte_cal = 10 if 0 < comprimento_fronte < 10 else comprimento_fronte
            largura_fronte_cal = 10 if 0 < largura_fronte < 10 else largura_fronte
            valor_fronte = comprimento_fronte_cal * largura_fronte_cal * material.valor / 10000
            valor_total_criar += valor_fronte

        # **Cálculo da Pedra de Box**
        if tipo_produto == 'Pedra de Box':
            valor_pedra_box = (valor_base) + 30
            valor_total_criar += valor_pedra_box

        # **Adicionando o valor das cubas**
        if tipo_cuba:
            valor_cuba = cuba_valores.get(tipo_cuba, 0)
            valor_total_criar += valor_cuba * quantidade_cubas

            # **Cálculo da Cuba Esculpida**
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


                valor_cuba_esculpida = m2_cuba * material.valor * quantidade_cubas + 175
                valor_total_criar += valor_cuba_esculpida

        # **Adicionando o valor do cooktop**
        if tem_cooktop == 'Sim':
            valor_total_criar += cooktop_valor

        # **Adicionando outros custos**
        valor_total_criar += outros_custos

        valor_total_criar *= quantidade

        valor_rt = 0.0  # Inicializa valor_rt como 0.0 para evitar erros
        if rt == 'Sim' and rt_percentual > 0:
            # Fórmula corrigida para usar o rt_percentual em forma numérica
            valor_rt = valor_total_criar / (1 - rt_percentual / 100) - valor_total_criar
            valor_total = valor_total_criar + valor_rt
        else:
            valor_total = valor_total_criar + valor_rt

        
        modelo_cuba = request.form.get("modelo_cuba", "").strip()
        if not modelo_cuba:  
            modelo_cuba = "Normal"  # Define "Normal" como padrão se estiver vazio

         # Criando e salvando o orçamento
        if cliente_id and material_id:
            novo_orcamento = Orcamento(
                cliente_id=cliente_id,
                tipo_produto=tipo_produto,
                material_id=material_id,
                quantidade=quantidade,
                comprimento=comprimento,
                largura=largura,
                outros_custos=outros_custos,
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
            # Salvar no banco de dados
            db.session.add(novo_orcamento)
            db.session.commit()

            # Atualiza os IDs selecionados
            selected_cliente_id = int(cliente_id)
            selected_material_id = int(material_id)

        return redirect(url_for('listar_orcamentos'))

    # Recupera os dados do banco de dados
    # Verifica se o usuário está logado
    user_cpf = session.get('user_cpf')

    if not user_cpf:
        flash("Faça login para acessar os orçamentos.", "error")
        return redirect(url_for('login'))

    # Busca os orçamentos corretamente
    if session.get('admin'):  
        # Admin vê todos os orçamentos e os nomes dos usuários que criaram
        orcamentos = db.session.query(
            Orcamento,
            Usuario.nome.label('nome_usuario')
        ).join(Usuario, Orcamento.dono == Usuario.cpf).all()

        clientes = Cliente.query.order_by(Cliente.nome).all()

    else:
        # Usuário comum vê apenas os seus próprios orçamentos
        orcamentos = db.session.query(
            Orcamento,
            Usuario.nome.label('nome_usuario')
        ).join(Usuario, Orcamento.dono == Usuario.cpf).filter(Orcamento.dono == user_cpf).all()

        clientes = Cliente.query.filter_by(dono=user_cpf).order_by(Cliente.nome).all()

    # Materiais são compartilhados entre todos os usuários
    materiais = Material.query.order_by(Material.nome).all()

    # Verifica se o usuário logado é administrador
    is_admin = session.get('admin', False)

    
    return render_template(
        'orcamentos.html',
        orcamentos=orcamentos,
        clientes=clientes,
        materiais=materiais,
        is_admin=is_admin  # Passando a variável para o template
    )

    
import re  # Para usar expressões regulares

def formatar_telefone(telefone):
    """ Formata o telefone para o padrão (XX) XXXXX-XXXX """
    telefone = re.sub(r'\D', '', telefone)  # Remove tudo que não for número
    if len(telefone) == 11:
        return f"({telefone[:2]}) {telefone[2:7]}-{telefone[7:]}"
    elif len(telefone) == 10:
        return f"({telefone[:2]}) {telefone[2:6]}-{telefone[6:]}"
    return telefone  # Retorna como está se não tiver o formato correto

def formatar_documento(documento):
    """ Formata CPF ou CNPJ automaticamente """

    # Remove qualquer caractere que não seja número
    documento = re.sub(r'\D', '', documento)

    if len(documento) == 11:  # CPF
        return f"{documento[:3]}.{documento[3:6]}.{documento[6:9]}-{documento[9:]}"
    
    elif len(documento) == 14:  # CNPJ
        return f"{documento[:2]}.{documento[2:5]}.{documento[5:8]}/{documento[8:12]}-{documento[12:]}"
    
    return documento  # Retorna o mesmo valor se não for CPF nem CNPJ

@app.route('/clientes', methods=['GET', 'POST'])
def clientes():
    if 'user_cpf' not in session:  # Se não estiver logado, redireciona para login
        return redirect(url_for('login'))

    if request.method == 'POST':
        nome = request.form['nome']
        endereco = request.form.get('endereco', '')
        telefone = request.form.get('telefone', '')
        documento = request.form.get('cpf_cnpj', '')
        dono = session['user_cpf']  # Define o dono como o CPF do usuário logado

        # Formatar os dados antes de salvar no banco
        telefone = formatar_telefone(telefone)
        documento = formatar_documento(documento)

        # Verifica se o cliente já existe pelo nome e dono
        cliente_existente = Cliente.query.filter_by(telefone=telefone, dono=dono).first()
        if cliente_existente:
            flash("Esse cliente já está cadastrado!", "error")
            return redirect(url_for('clientes'))

        # Criar novo cliente (agora com dono)
        novo_cliente = Cliente(nome=nome, endereco=endereco, telefone=telefone, documento=documento, dono=dono)

        db.session.add(novo_cliente)
        db.session.commit()

        flash("Cliente cadastrado com sucesso!", "success")
        return redirect(url_for('clientes'))

    # Verifica se o usuário logado é administrador
    is_admin = session.get('admin', False)

    if is_admin:
        # Admin vê todos os clientes e os usuários que os criaram
        clientes = db.session.query(Cliente, Usuario.nome.label('nome_usuario'))\
                             .join(Usuario, Cliente.dono == Usuario.cpf)\
                             .order_by(Cliente.nome).all()
    else:
        # Usuário comum vê apenas os clientes que ele cadastrou
        clientes = db.session.query(Cliente, Usuario.nome.label('nome_usuario'))\
                             .join(Usuario, Cliente.dono == Usuario.cpf)\
                             .filter(Cliente.dono == session['user_cpf'])\
                             .order_by(Cliente.nome).all()

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
        novo_documento = request.form['documento']

        # Verificar se outro cliente já usa este documento
        documento_existente = Cliente.query.filter(Cliente.documento == novo_documento, Cliente.id != id).first()
        if documento_existente:
            flash("Erro: Este CPF/CNPJ já está cadastrado em outro cliente!", "error")
            return redirect(url_for('editar_cliente', id=id))

        # Atualizar os dados do cliente
        cliente.nome = request.form['nome']
        cliente.endereco = request.form['endereco']
        cliente.telefone = request.form['telefone']
        cliente.documento = novo_documento
        db.session.commit()

        
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
        orcamento.material_id = request.form['material_id']
        orcamento.quantidade = int(request.form.get('quantidade', orcamento.quantidade))
        orcamento.comprimento = float(request.form.get('comprimento', orcamento.comprimento or 0)or 0)
        orcamento.largura = float(request.form.get('largura', orcamento.largura or 0)or 0)
        orcamento.outros_custos = float(request.form.get('outros_custos', orcamento.outros_custos or 0)or 0)
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
            'Embutir': 225,
            'Esculpida': 0,
            'Cuba Tradicional Inox': 225,
            'Apoio Cliente': 125,
            'Embutida Cliente': 125,
            'Gourmet Cliente': 225,
            'Tanque Inox': 500
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
            
                valor_cuba_esculpida = m2_cuba * material.valor * orcamento.quantidade_cubas + 175
                valor_total_criar += valor_cuba_esculpida

                # **Definindo o valor fixo do cooktop**
        cooktop_valor = 50  # Valor fixo para o cooktop

        # **Adicionando o valor do cooktop**
        if orcamento.tem_cooktop == 'Sim':
            valor_total_criar += cooktop_valor
        else:
            orcamento.tem_cooktop = 'Não'  # Define explicitamente como "Não" se não for "Sim"
        print(f"Valor do campo tem_cooktop: {orcamento.tem_cooktop}")


        # **Adicionando outros custos**
        valor_total_criar += orcamento.outros_custos

        valor_total_criar *= orcamento.quantidade

        valor_rt = 0.0
        # **Aplicando RT**
        if orcamento.rt == 'Sim' and orcamento.rt_percentual > 0:
            valor_rt = valor_total_criar / (1 - orcamento.rt_percentual / 100) - valor_total_criar
            orcamento.valor_total = valor_total_criar + valor_rt
        else:
            orcamento.valor_total = valor_total_criar + valor_rt

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

        usuario = Usuario.query.filter_by(cpf=cpf).first()

        if usuario and usuario.check_senha(senha):  # Agora todas as senhas são comparadas corretamente
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
        nome = request.form.get('nome')  # Pegando o nome do usuário
        cpf = request.form.get('cpf')
        senha = request.form.get('senha')

        if not nome or not cpf or not senha:
            flash("Todos os campos são obrigatórios!", "error")
            return redirect(url_for('criar_usuario'))

        try:
            novo_usuario = Usuario(nome=nome, cpf=cpf, is_admin=False)
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
        return redirect(url_for('login'))  # Redireciona se não estiver logado

    usuario = Usuario.query.filter_by(cpf=session['user_cpf']).first()

    if not usuario:
        flash("Erro: Usuário não encontrado!", "error")
        return redirect(url_for('index'))

    if request.method == 'POST':
        nova_senha = request.form['nova_senha']

        if not nova_senha or len(nova_senha) < 6:
            flash("A senha deve ter pelo menos 6 caracteres!", "error")
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
        usuario.nome = request.form['nome']  # Atualiza o nome do usuário
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

    # Buscar os IDs dos orçamentos salvos
    ids = [int(id) for id in orcamento_salvo.orcamentos_ids.split(",")]

    # Buscar os detalhes dos orçamentos vinculados
    orcamentos = Orcamento.query.filter(Orcamento.id.in_(ids)).all()

    # Calcular o valor total
    valor_total_final = sum(o.valor_total for o in orcamentos)

    # ✅ Adicionando a URL da logo para o template
    logo_url = "https://orcamento-t9w2.onrender.com/static/logo.jpg"

    return render_template(
        "detalhes_orcamento_salvo.html",
        logo_url=logo_url,  # 🔥 Agora a logo é enviada para o HTML
        codigo_orcamento=orcamento_salvo.codigo,
        data_salvo=orcamento_salvo.data_salvo,
        cliente_nome=orcamentos[0].cliente.nome if orcamentos else "Desconhecido",
        orcamentos=orcamentos,
        valor_total_final="R$ {:,.2f}".format(valor_total_final).replace(",", "X").replace(".", ",").replace("X", ".")
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
    valor_total_final = sum(o.valor_total for o in orcamentos)

    # ✅ Renderizamos o HTML normalmente sem a logo
    rendered_html = render_template(
        "detalhes_orcamento_salvo.html",
        codigo_orcamento=orcamento_salvo.codigo,
        data_salvo=orcamento_salvo.data_salvo,
        cliente_nome=orcamentos[0].cliente.nome if orcamentos else "Desconhecido",
        orcamentos=orcamentos,
        valor_total_final="R$ {:,.2f}".format(valor_total_final).replace(",", "X").replace(".", ",").replace("X", "."),
        pdf=True
    )

    # ✅ Criamos um arquivo temporário para armazenar o PDF sem a logo
    temp_pdf_path = "/tmp/temp_orcamento.pdf"
    HTML(string=rendered_html, base_url="https://orcamento-t9w2.onrender.com").write_pdf(temp_pdf_path)

    # ✅ Definição do caminho local para a logo SEM precisar baixar
    logo_path = "static/logo.jpg"

    # ✅ Inserir a logo no PDF diretamente do caminho local
    final_pdf_path = "/tmp/final_orcamento.pdf"
    doc = fitz.open(temp_pdf_path)

   

    if os.path.exists(logo_path):  # 🔥 Apenas adiciona a logo se o arquivo existir
        page = doc[0]  # Pega a primeira página do PDF
        page_width = page.rect.width  # Largura total da página
        page_height = page.rect.height  # Altura total da página

        logo_width = 240  # Ajuste conforme necessário
        logo_height = 120  # Ajuste conforme necessário

        # 🔥 Posiciona a logo no canto superior direito
        rect = fitz.Rect(page_width - logo_width - -20, 20, page_width - -20, 20 + logo_height)

        page.insert_image(rect, filename=logo_path)
    else:
        print("⚠️ Aviso: A logo não foi adicionada porque o arquivo local não foi encontrado.")

    doc.save(final_pdf_path)  # Salva o PDF final com a logo (ou sem, caso não exista)
    doc.close()

    # ✅ Retornamos o PDF final com a logo inserida
    with open(final_pdf_path, "rb") as pdf_file:
        pdf_bytes = pdf_file.read()

    response = make_response(pdf_bytes)
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = f"inline; filename=orcamento_{codigo}.pdf"

    # ✅ Limpa os arquivos temporários
    os.remove(temp_pdf_path)
    os.remove(final_pdf_path)

    return response


@app.route('/orcamentos/editar_material_selecionados', methods=['POST'])
def editar_material_selecionados():
    data = request.get_json()
    orcamento_ids = data.get('orcamento_ids', [])
    material_id = data.get('material_id')

    if not orcamento_ids or not material_id:
        return jsonify({'erro': 'Dados inválidos.'}), 400

    material = Material.query.get(material_id)
    if not material:
        return jsonify({'erro': 'Material não encontrado.'}), 404

    cuba_valores = {
        'Embutir': 225,
        'Esculpida': 0,
        'Cuba Tradicional Inox': 225,
        'Apoio Cliente': 125,
        'Embutida Cliente': 125,
        'Gourmet Cliente': 225,
        'Tanque Inox': 500
    }

    cooktop_valor = 50  # Valor fixo para cooktop

    # 🔥 Coletar IDs de orçamentos salvos que serão afetados
    orcamentos_salvos_para_atualizar = set()

    orcamentos = Orcamento.query.filter(Orcamento.id.in_(orcamento_ids)).all()

    for orcamento in orcamentos:
        orcamento.material_id = material_id

        valor_total_criar = 0

        comprimento_cal = max(orcamento.comprimento, 10)
        largura_cal = max(orcamento.largura, 10)

        valor_base = material.valor * (comprimento_cal * largura_cal / 10000)

        if orcamento.tipo_produto in ['Bancada', 'Lavatorio']:
            if material.valor < 1000:
                valor_base *= 1.3
            elif material.valor < 2000:
                valor_base *= 1.15
            elif material.valor < 1000000:
                valor_base *= 1.1

        if orcamento.tipo_produto == 'Ilharga Bipolida' and material.valor < 1000000:
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
                largura_alisar_cal = max(orcamento.largura_alisar, 10)
                area_nicho += ((comprimento_cal + (largura_alisar_cal * 2)) * largura_alisar_cal * 2) + \
                              ((largura_cal + (largura_alisar_cal * 2)) * largura_alisar_cal * 2)

            valor_nicho = (area_nicho / 10000) * material.valor + 150
            valor_total_criar = valor_nicho

        # Saia
        if orcamento.tipo_produto in ['Ilharga', 'Ilharga Bipolida', 'Bancada', 'Lavatorio']:
            comprimento_saia_cal = max(orcamento.comprimento_saia or 0, 10)
            largura_saia_cal = max(orcamento.largura_saia or 0, 10)
            valor_saia = comprimento_saia_cal * largura_saia_cal * material.valor / 10000
            valor_total_criar += valor_saia

        # Fronte
        if orcamento.tipo_produto in ['Bancada', 'Lavatorio']:
            comprimento_fronte_cal = max(orcamento.comprimento_fronte or 0, 10)
            largura_fronte_cal = max(orcamento.largura_fronte or 0, 10)
            valor_fronte = comprimento_fronte_cal * largura_fronte_cal * material.valor / 10000
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

                valor_cuba_esculpida = m2_cuba * material.valor * (orcamento.quantidade_cubas or 1) + 175
                valor_total_criar += valor_cuba_esculpida

        # Cooktop
        if orcamento.tem_cooktop == 'Sim':
            valor_total_criar += cooktop_valor

        # Outros custos
        valor_total_criar += orcamento.outros_custos or 0

        # Quantidade
        valor_total_criar *= orcamento.quantidade

        # RT
        if orcamento.rt == 'Sim' and (orcamento.rt_percentual or 0) > 0:
            valor_rt = valor_total_criar / (1 - orcamento.rt_percentual / 100) - valor_total_criar
            valor_total_final = valor_total_criar + valor_rt
        else:
            valor_total_final = valor_total_criar

        orcamento.valor_total = valor_total_final

    db.session.commit()

    # 🔥 Atualizar todos os orçamentos salvos afetados
    orcamentos_salvos = OrcamentoSalvo.query.filter(
        db.or_(*[OrcamentoSalvo.orcamentos_ids.like(f"%{id}%") for id in orcamento_ids])
    ).all()

    for orcamento_salvo in orcamentos_salvos:
        atualizar_valor_orcamento_salvo(orcamento_salvo.id)

    return jsonify({'mensagem': 'Materiais atualizados, valores recalculados e orçamentos salvos atualizados.'})



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
                    tipo_produto = original.tipo_produto,
                    material_id = original.material_id,
                    quantidade = original.quantidade,
                    comprimento = original.comprimento,
                    largura = original.largura,
                    outros_custos = original.outros_custos,
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
                    data = datetime.utcnow(),
                    user_cpf = original.user_cpf,
                    orcamento_salvo_id = None  # não herda vínculo
                )
                db.session.add(novo_orcamento)

        db.session.commit()
        return jsonify({'success': True})

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({'success': False, 'error': traceback.format_exc()}), 500






if __name__ == '__main__':
    criar_banco()
    app.run(debug=True)
