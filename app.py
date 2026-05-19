# 📌 Imports de Bibliotecas Externas
from flask import Flask, render_template, make_response, request, redirect, url_for, jsonify, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from pytz import timezone
from weasyprint import HTML
from sqlalchemy import or_
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
    prazo_entrega = db.Column(db.Integer, default=15, nullable=False)
    desconto_avista = db.Column(db.Integer, default=5, nullable=False)
    desconto_parcelado = db.Column(db.Integer, default=10, nullable=False)
    observacoes = db.Column(db.Text, default="Medidas sujeitas a confirmação no local. Valores válidos por 7 dias.", nullable=False)
    exclude_payments = db.Column(db.String(50), default='')
    desenhos_ordem_servico = db.relationship('DesenhoOrdemServico', backref='orcamento', lazy=True)
    desenho_ordem_servico = db.Column(db.Text, nullable=True)
    max_parcelas = db.Column(db.Integer, nullable=True)

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
    profundidade_nicho = db.Column(db.Float, default=0.0)
    tem_fundo = db.Column(db.String(50), default="Sim")
    tem_alisar = db.Column(db.String(50), default="Não")
    largura_alisar = db.Column(db.Float, default=0.0)

class DesenhoOrdemServico(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    orcamento_salvo_codigo = db.Column(db.String, db.ForeignKey('orcamento_salvo.codigo', ondelete='CASCADE'), nullable=False)
    desenho_data = db.Column(db.Text, nullable=False)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)


# Função para inicializar o banco de dados
def criar_banco():
    with app.app_context():
        db.create_all()

@app.route('/orcamento')
def configurador_3d():
    logado = 'user_cpf' in session
    return render_template('configurador_3d.html', logado=logado)

@app.route('/api/materiais')
def api_materiais():
    materiais = Material.query.order_by(Material.nome).all()
    return jsonify([{'id': m.id, 'nome': m.nome} for m in materiais])

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

        dono_cpf = session.get('user_cpf', '12233344441')

        cliente = Cliente.query.filter_by(telefone=telefone, dono=dono_cpf).first()
        if not cliente:
            cliente = Cliente(nome=nome, telefone=telefone, endereco=endereco, dono=dono_cpf)
            db.session.add(cliente)
            db.session.flush()

        cuba_valores = {
            'Embutida': 225, 'Sobreposta': 125, 'Esculpida': 175,
            'Tradicional Inox': 225, 'Tanque Inox': 500,
            'Apoio Cliente': 125, 'Embutida Cliente': 125,
            'Gourmet Cliente': 225, 'Sobrepor Cliente': 125,
            'Tanque Inox Cliente': 225
        }

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
            for side, dim in sides_dims:
                bt = bordas_cfg.get(side, 'livre')
                if bt == 'saia':
                    comp_saia += dim
                    larg_saia = max(larg_saia, saia_largs.get(side, 10))
                elif bt == 'fronte':
                    comp_fronte += dim
                    larg_fronte = max(larg_fronte, alts.get(side, 10))
                elif bt == 'ilharga':
                    comp_saia += alts.get(side, 92)
                    larg_saia = max(larg_saia, saia_largs.get(side, 10))
            return comp_saia, larg_saia, comp_fronte, larg_fronte

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
                           produto_nome=''):
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

                if tipo_produto == 'Ilharga Bipolida' and valor_base < 1000000:
                    valor_base *= 1.15

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

                tipo_cuba_cap = tipo_cuba.capitalize() if tipo_cuba else ''
                if tipo_cuba_cap:
                    vc = cuba_valores.get(tipo_cuba_cap, 0)
                    valor_total += vc * max(qtd_cubas, 1)
                    if tipo_cuba_cap == 'Esculpida' and comp_cuba > 0:
                        m2_cuba = ((comp_cuba*larg_cuba*2)+(comp_cuba*2+larg_cuba*2)*prof_cuba)/10000
                        valor_total += m2_cuba * mat.valor * max(qtd_cubas, 1)

                if tem_cooktop == 'Sim':
                    valor_total += 50

                valor_total = round(valor_total, 2)

                prod_id = get_or_create_produto(produto_nome) if produto_nome else None

                orc = Orcamento(
                    cliente_id=cliente.id, ambiente_id=None,
                    descricao_id=None, produto_id=prod_id,
                    tipo_produto=tipo_produto, material_id=mat.id,
                    quantidade=1, comprimento=comprimento, largura=largura,
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

                def cubas_na_secao(secao):
                    if not pcfg.get('cuba'):
                        return '', 0, 0, 0, 0
                    qtd = pcfg.get('cubaQtd', 1)
                    c1_here = pcfg.get('cubaLocal') == secao
                    c2_here = qtd >= 2 and pcfg.get('cuba2Local') == secao
                    if c1_here and c2_here:
                        return pcfg.get('tipoCuba', ''), 2, pcfg.get('cubaComp', 0), pcfg.get('cubaLarg', 0), pcfg.get('cubaAlt', 0)
                    if c1_here:
                        return pcfg.get('tipoCuba', ''), 1, pcfg.get('cubaComp', 0), pcfg.get('cubaLarg', 0), pcfg.get('cubaAlt', 0)
                    if c2_here:
                        return pcfg.get('tipoCuba2', ''), 1, pcfg.get('cubaComp2', 0), pcfg.get('cubaLarg2', 0), pcfg.get('cubaAlt2', 0)
                    return '', 0, 0, 0, 0

                if has_molhada:
                    comp_m = pcfg.get('compMolhada', 120)
                    prof_m = pcfg.get('profMolhada', 60)
                    cs, ls, cf, lf = calc_saia_fronte([('fundo', comp_m), ('frente', comp_m)], bordas, borda_alts, borda_saia_larg)
                    tc, qc, cc, lc, pc = cubas_na_secao('molhada')
                    criar_item_p('Bancada', comp_m, prof_m, cs, ls, cf, lf,
                              tipo_cuba=tc, qtd_cubas=qc,
                              comp_cuba=cc, larg_cuba=lc, prof_cuba=pc,
                              produto_nome='Bancada Molhada')

                if has_seca:
                    comp_s = pcfg.get('compSeca', 120)
                    prof_s = pcfg.get('profSeca', 60)
                    cs, ls, cf, lf = calc_saia_fronte([('fundo', comp_s), ('frente', comp_s)], bordas, borda_alts, borda_saia_larg)
                    tc, qc, cc, lc, pc = cubas_na_secao('seca')
                    cook = 'Sim' if pcfg.get('cooktop') else 'Não'
                    criar_item_p('Bancada', comp_s, prof_s, cs, ls, cf, lf,
                              tipo_cuba=tc, qtd_cubas=qc,
                              comp_cuba=cc, larg_cuba=lc, prof_cuba=pc,
                              tem_cooktop=cook,
                              produto_nome='Bancada Seca')

                if is_l:
                    comp_l = pcfg.get('compL', 120)
                    prof_l = pcfg.get('profL', 60)
                    cs, ls, cf, lf = calc_saia_fronte([('fundo', comp_l), ('frente', comp_l), ('l_esquerda', prof_l), ('l_fundo', comp_l)], bordas, borda_alts, borda_saia_larg)
                    criar_item_p('Bancada', comp_l, prof_l, cs, ls, cf, lf,
                              produto_nome='Bancada em L')

                for side_key in ['esquerda', 'direita']:
                    if bordas.get(side_key) == 'ilharga':
                        alt = borda_alts.get(side_key, 92)
                        prof_ilh = pcfg.get('profMolhada', 60) if has_molhada else pcfg.get('profSeca', 60)
                        saia_frente = borda_saia_larg.get('frente', 10) if bordas.get('frente') in ['saia'] else 0
                        saia_fundo = borda_saia_larg.get('fundo', 10) if bordas.get('fundo') in ['saia'] else 0
                        n_saias = (1 if saia_frente > 0 else 0) + (1 if saia_fundo > 0 else 0)
                        cs_ilh = alt * n_saias
                        ls_ilh = max(saia_frente, saia_fundo) if cs_ilh > 0 else 0
                        criar_item_p('Ilharga', alt, prof_ilh, cs_ilh, ls_ilh, 0, 0,
                                  produto_nome='Ilharga')

            elif produto == 'lavatorio':
                comp = pcfg.get('compGen', 120)
                prof = pcfg.get('profGen', 55)
                lav_sides = [('fundo', comp), ('frente', comp), ('esquerda', prof), ('direita', prof)]
                if pcfg.get('lavModelo') == 'violao':
                    lav_sides.append(('direita2', prof))
                cs, ls, cf, lf = calc_saia_fronte(lav_sides, bordas, borda_alts, borda_saia_larg)
                tc = pcfg.get('tipoCuba', '') if pcfg.get('cuba') else ''
                qc = pcfg.get('cubaQtd', 1) if tc else 0
                lav_modelo = pcfg.get('lavModelo', 'retangular')
                lav_nome = 'Lavatorio Violao' if lav_modelo == 'violao' else 'Lavatorio Retangular'
                criar_item_p('Lavatorio', comp, prof, cs, ls, cf, lf,
                          tipo_cuba=tc, qtd_cubas=qc,
                          comp_cuba=pcfg.get('cubaComp',0), larg_cuba=pcfg.get('cubaLarg',0), prof_cuba=pcfg.get('cubaAlt',0),
                          produto_nome=lav_nome)

                for side_key in ['esquerda', 'direita', 'direita2']:
                    if bordas.get(side_key) == 'ilharga':
                        alt = borda_alts.get(side_key, 92)
                        saia_frente = borda_saia_larg.get('frente', 10) if bordas.get('frente') == 'saia' else 0
                        saia_fundo = borda_saia_larg.get('fundo', 10) if bordas.get('fundo') == 'saia' else 0
                        n_saias = (1 if saia_frente > 0 else 0) + (1 if saia_fundo > 0 else 0)
                        cs_ilh = alt * n_saias
                        ls_ilh = max(saia_frente, saia_fundo) if cs_ilh > 0 else 0
                        criar_item_p('Ilharga', alt, prof, cs_ilh, ls_ilh, 0, 0,
                                  produto_nome='Ilharga')

            elif produto == 'nicho':
                criar_item_p('Nicho', pcfg.get('nichoLarg', 60), pcfg.get('nichoAlt', 30), 0, 0, 0, 0,
                           prof_nicho=pcfg.get('nichoProf', 12),
                           tem_fundo='Sim' if pcfg.get('nichoFundo', True) else 'Não',
                           tem_alisar='Sim' if pcfg.get('nichoAlisar', False) else 'Não',
                           larg_alisar=pcfg.get('nichoAlisarMedida', 0),
                           produto_nome='Nicho')

            elif produto == 'soleira':
                qtd_soleira = int(pcfg.get('soleiraQtd', 1))
                for _ in range(max(qtd_soleira, 1)):
                    criar_item_p('Soleira', pcfg.get('soleiraLarg', 80), pcfg.get('soleiraProf', 15), 0, 0, 0, 0,
                               produto_nome='Soleira')

        processar_produto_cfg(cfg)

        for extra in cfg.get('produtosExtras', []):
            if extra.get('produto'):
                processar_produto_cfg(extra)

        if not orcamento_ids:
            return jsonify({'success': False, 'error': 'Nenhum item gerado'}), 400

        orc_salvo = OrcamentoSalvo(
            orcamentos_ids=','.join(orcamento_ids),
            valor_total=sum(Orcamento.query.get(int(i)).valor_total for i in orcamento_ids),
            criado_por='Configurador Online',
            tipo_cliente='Cliente Online'
        )
        orc_salvo.gerar_codigo()
        db.session.add(orc_salvo)
        db.session.flush()

        desenho_data = cfg.get('desenho', '')
        if desenho_data:
            desenho = DesenhoOrdemServico(
                orcamento_salvo_codigo=orc_salvo.codigo,
                desenho_data=desenho_data
            )
            db.session.add(desenho)

        db.session.commit()

        return jsonify({'success': True, 'codigo': orc_salvo.codigo})

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/ver_desenho/<codigo>')
def ver_desenho(codigo):
    desenho = DesenhoOrdemServico.query.filter_by(
        orcamento_salvo_codigo=codigo
    ).order_by(DesenhoOrdemServico.data_criacao.desc()).first()
    if not desenho:
        return 'Desenho nao encontrado', 404
    return f'''<!DOCTYPE html>
<html><head><title>Desenho - {codigo}</title>
<style>body{{margin:0;background:#1a1a2e;display:flex;justify-content:center;align-items:center;min-height:100vh}}
img{{max-width:95vw;max-height:95vh;border-radius:8px;box-shadow:0 4px 20px rgba(0,0,0,.5)}}</style></head>
<body><img src="{desenho.desenho_data}" alt="Desenho {codigo}"></body></html>'''

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
                area_nicho = ((comprimento_cal + 4) * (largura_cal + 4)) + (((comprimento_cal + 4) * profundidade_nicho_cal) * 2) + (((largura_cal + 4) * profundidade_nicho_cal) * 2)
            else:
                area_nicho = ((comprimento_cal + 4) + (largura_cal + 4)) * profundidade_nicho_cal * 2

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
        descricoes=descricoes,
        produtos=produtos,
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

    # 🔥 EXCLUIR FISICAMENTE (apenas da tabela Orcamento)
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

        return render_template(
            'detalhes_orcamento.html',
            orcamentos=orcamentos,
            ambientes_agrupados=ambientes_agrupados,  # NOVO: estrutura de agrupamento
            cliente_nome=cliente_nome,
            valor_total_final=valor_total_formatado,
            valor_total_float=valor_total_float,
            telefone_usuario=telefone_usuario,
            # Adicionar valores padrão para manter compatibilidade com o template
            prazo_entrega=15,
            desconto_avista=5,
            desconto_parcelado=10,
            observacoes="Medidas sujeitas a confirmação no local. Valores válidos por 7 dias.",
            exclude_payments=[]
        )

    except Exception as e:
        return f"Erro ao carregar detalhes dos orçamentos: {str(e)}", 500

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        cpf = request.form['cpf'].strip()
        senha = request.form['senha']

        print(f"Tentando login com CPF: [{cpf}]")  # Debug

        # 🔥 MÚLTIPLAS TENTATIVAS:
        # 1. CPF exatamente como digitado
        usuario = Usuario.query.filter_by(cpf=cpf).first()
        
        # 2. CPF sem formatação
        if not usuario:
            cpf_limpo = re.sub(r'[\.\-]', '', cpf)
            usuario = Usuario.query.filter_by(cpf=cpf_limpo).first()
            print(f"Tentando com CPF limpo: [{cpf_limpo}]")
        
        # 3. CPF com formatação padrão (se o usuário digitou sem formatação)
        if not usuario and len(cpf) == 11 and cpf.isdigit():
            cpf_formatado = f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"
            usuario = Usuario.query.filter_by(cpf=cpf_formatado).first()
            print(f"Tentando com CPF formatado: [{cpf_formatado}]")

        if usuario:
            print(f"Usuário encontrado: {usuario.nome}, CPF: [{usuario.cpf}]")
            
            if usuario.check_senha(senha):
                session['user_cpf'] = usuario.cpf
                session['admin'] = usuario.is_admin
                print("✅ Login bem-sucedido!")
                return redirect(url_for('index'))
            else:
                print("❌ Senha incorreta")
        else:
            print("❌ Usuário não encontrado")

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

    codigos_com_desenho = set(
        d.orcamento_salvo_codigo for d in DesenhoOrdemServico.query.with_entities(
            DesenhoOrdemServico.orcamento_salvo_codigo
        ).all()
    )

    return render_template("orcamentos_salvos.html",
                           clientes=clientes,
                           usuarios=usuarios,
                           orcamentos=resultado,
                           codigos_com_desenho=codigos_com_desenho)






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
    logo_url = "https://orcamento-t9w2.onrender.com/static/logo.jpg"
    
    # Obter informações do usuário
    usuario = Usuario.query.filter_by(cpf=session.get('user_cpf')).first()
    telefone_usuario = usuario.telefone if usuario else ""
    
    # Obter informações do cliente do primeiro orçamento
    cliente_nome = orcamentos[0].cliente.nome if orcamentos else "Desconhecido"
    
    # Obter configurações do rodapé do orçamento salvo (com valores padrão como fallback)
    prazo_entrega = orcamento_salvo.prazo_entrega if orcamento_salvo.prazo_entrega is not None else 15
    desconto_avista = orcamento_salvo.desconto_avista if orcamento_salvo.desconto_avista is not None else 5
    desconto_parcelado = orcamento_salvo.desconto_parcelado if orcamento_salvo.desconto_parcelado is not None else 10
    observacoes = orcamento_salvo.observacoes if orcamento_salvo.observacoes is not None else "Medidas sujeitas a confirmação no local. Valores válidos por 7 dias."
    
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
        prazo_entrega=prazo_entrega,
        desconto_avista=desconto_avista,
        desconto_parcelado=desconto_parcelado,
        observacoes=observacoes,
        exclude_payments=exclude_payments,
        # Passar parâmetro para saber se estamos em modo PDF ou não
        pdf=False,
        # Passar o usuário atual para verificar permissões no template
        usuario_atual=usuario,
        is_admin=is_admin,
        max_parcelas = orcamento_salvo.max_parcelas
    )

def recriar_agrupamentos_orcamento(codigo_orcamento):
    """
    Função auxiliar para recriar os agrupamentos de um orçamento salvo.
    Estrutura: Ambiente -> Descrição -> Tipo de Produto -> Lista de Produtos
    """
    try:
        orcamento_salvo = OrcamentoSalvo.query.filter_by(codigo=codigo_orcamento).first()
        
        if not orcamento_salvo:
            print(f"⚠️ Orçamento salvo não encontrado: {codigo_orcamento}")
            return None
        
        # Extrair IDs dos orçamentos (com validação)
        ids_str = orcamento_salvo.orcamentos_ids
        if not ids_str or not ids_str.strip():
            print(f"⚠️ Lista de IDs vazia para orçamento: {codigo_orcamento}")
            return {}
        
        ids = []
        for id_str in ids_str.split(','):
            id_str = id_str.strip()
            if id_str and id_str.isdigit():
                ids.append(int(id_str))
            else:
                print(f"⚠️ ID inválido ignorado: '{id_str}'")
        
        if not ids:
            print(f"⚠️ Nenhum ID válido encontrado para orçamento: {codigo_orcamento}")
            return {}
        
        # Buscar orçamentos
        orcamentos = Orcamento.query.filter(Orcamento.id.in_(ids)).all()
        
        if not orcamentos:
            print(f"⚠️ Nenhum orçamento encontrado para os IDs: {ids}")
            return {}
        
        # Reagrupar por ambiente -> descrição -> tipo de produto
        ambientes_agrupados = {}
        
        for orcamento in orcamentos:
            # Obter nome do ambiente
            if orcamento.ambiente:
                ambiente_nome = orcamento.ambiente.nome
            else:
                ambiente_nome = 'Sem Ambiente'
                print(f"ℹ️ Orçamento {orcamento.id} sem ambiente definido")
            
            # Inicializar o ambiente se não existir
            if ambiente_nome not in ambientes_agrupados:
                ambientes_agrupados[ambiente_nome] = {}
            
            # Obter nome da descrição
            if orcamento.descricao:
                descricao_nome = orcamento.descricao.nome
            else:
                descricao_nome = 'Sem Descrição'
                print(f"ℹ️ Orçamento {orcamento.id} sem descrição definida")
            
            # Inicializar a descrição se não existir
            if descricao_nome not in ambientes_agrupados[ambiente_nome]:
                ambientes_agrupados[ambiente_nome][descricao_nome] = {}
            
            # Obter tipo de produto
            tipo_produto = orcamento.tipo_produto
            if not tipo_produto:
                tipo_produto = 'Não especificado'
                print(f"ℹ️ Orçamento {orcamento.id} sem tipo de produto definido")
            
            # Inicializar o tipo de produto se não existir
            if tipo_produto not in ambientes_agrupados[ambiente_nome][descricao_nome]:
                ambientes_agrupados[ambiente_nome][descricao_nome][tipo_produto] = []
            
            # Adicionar o orçamento à lista correta
            ambientes_agrupados[ambiente_nome][descricao_nome][tipo_produto].append(orcamento)
        
        # Log para debug
        print(f"✅ Agrupamentos recriados para {codigo_orcamento}:")
        for ambiente, descricoes in ambientes_agrupados.items():
            print(f"  📍 {ambiente}: {len(descricoes)} descrições")
            for descricao, tipos in descricoes.items():
                print(f"    📝 {descricao}: {len(tipos)} tipos de produto")
                total_itens = sum(len(produtos) for produtos in tipos.values())
                print(f"      📦 Total de itens nesta descrição: {total_itens}")
        
        return ambientes_agrupados
    
    except Exception as e:
        print(f"❌ Erro ao recriar agrupamentos para {codigo_orcamento}: {str(e)}")
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

    codigos_com_desenho = set(
        d.orcamento_salvo_codigo for d in DesenhoOrdemServico.query.with_entities(
            DesenhoOrdemServico.orcamento_salvo_codigo
        ).all()
    )

    return render_template('orcamentos_salvos.html', orcamentos=orcamentos, codigos_com_desenho=codigos_com_desenho)





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
        
        # 🔥 Excluir desenhos associados
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

    logo_url = "https://orcamento-t9w2.onrender.com/static/logo.jpg"
    
    usuario = Usuario.query.filter_by(cpf=session.get('user_cpf')).first()
    if not usuario:
        usuario = Usuario.query.filter_by(cpf='12233344441').first()
    telefone_usuario = usuario.telefone if usuario else ""

    # ✅ Valores do rodapé (com fallback)
    prazo_entrega = orcamento_salvo.prazo_entrega if orcamento_salvo.prazo_entrega is not None else 15
    desconto_avista = orcamento_salvo.desconto_avista if orcamento_salvo.desconto_avista is not None else 5
    desconto_parcelado = orcamento_salvo.desconto_parcelado if orcamento_salvo.desconto_parcelado is not None else 10
    observacoes = orcamento_salvo.observacoes if orcamento_salvo.observacoes is not None else "Medidas sujeitas a confirmação no local. Valores válidos por 7 dias."
    
    # ✅ NOVO: Obter max_parcelas (pode ser None)
    max_parcelas = orcamento_salvo.max_parcelas

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
        prazo_entrega=prazo_entrega,
        desconto_avista=desconto_avista,
        desconto_parcelado=desconto_parcelado,
        observacoes=observacoes,
        pdf=True,
        exclude_payments=exclude_payments,
        max_parcelas=max_parcelas   # <-- ESSENCIAL para evitar NameError
    )

    # 🔥 Geração do PDF com arquivos temporários (compatível com Windows)
    import tempfile
    with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_pdf:
        temp_pdf_path = temp_pdf.name

    with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as final_pdf:
        final_pdf_path = final_pdf.name

    HTML(string=rendered_html, base_url="https://orcamento-t9w2.onrender.com").write_pdf(temp_pdf_path)

    # Adicionar logo (se existir)
    import fitz  # PyMuPDF
    logo_path = "static/logo.jpg"
    doc = fitz.open(temp_pdf_path)
    if os.path.exists(logo_path):
        page = doc[0]
        page_width = page.rect.width
        page_height = page.rect.height
        logo_width = 210
        logo_height = 105
        rect = fitz.Rect(page_width - logo_width - -20, 20, page_width - -20, 20 + logo_height)
        page.insert_image(rect, filename=logo_path)
    doc.save(final_pdf_path)
    doc.close()

    # Ler PDF final e retornar
    with open(final_pdf_path, "rb") as pdf_file:
        pdf_bytes = pdf_file.read()

    response = make_response(pdf_bytes)
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = f"inline; filename=orcamento_{codigo}.pdf"

    # Limpar temporários
    os.unlink(temp_pdf_path)
    os.unlink(final_pdf_path)

    return response

@app.route('/orcamentos/editar_material_rt_selecionados', methods=['POST'])
def editar_material_rt_selecionados():
    data = request.get_json()
    orcamento_ids = data.get('orcamento_ids', [])
    cliente_id = data.get('cliente_id')
    material_id = data.get('material_id')
    rt = data.get('rt')
    rt_percentual = data.get('rt_percentual', 0.0)
    descricao_id = data.get('descricao_id')  # 🔥 NOVO: Adicionar descrição
    produto_id = data.get('produto_id')      # 🔥 NOVO: Adicionar produto

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
        
        # 🔥 NOVO: Atualizar produto apenas se foi fornecido
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

        if orcamento.tipo_produto == 'Ilharga Bipolida' and material_para_calculo.valor < 1000000:
            valor_base *= 1.15

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
                novo_orcamento = Orcamento(
                    cliente_id=original.cliente_id,
                    ambiente_id=original.ambiente_id,
                    descricao_id=original.descricao_id,  # 🔥 ADICIONAR DESCRIÇÃO
                    produto_id=original.produto_id,      # 🔥 ADICIONAR PRODUTO
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
                    profundidade_nicho=original.profundidade_nicho,
                    tem_fundo=original.tem_fundo,
                    tem_alisar=original.tem_alisar,
                    largura_alisar=original.largura_alisar,
                    valor_total=original.valor_total,
                    dono=original.dono,
                    data=datetime.now(br_tz)
                )

                db.session.add(novo_orcamento)
                db.session.flush()  # 🔥 Para obter o ID do novo orçamento
                novos_ids.append(novo_orcamento.id)

        db.session.commit()
        
        # 🔥 RETORNAR OS NOVOS IDs PARA SELEÇÃO AUTOMÁTICA
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
    
    if not orcamento_salvo:
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
    
    # ✅ Salvar as opções de pagamento excluídas
    exclude_payments = request.form.get('exclude_payments', '')
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
            Material.valor.label('valor_material')  # 🔥 ADICIONADO: valor do material
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
                'valor_material': row.valor_material if hasattr(row, 'valor_material') else 0,  # 🔥 NOVO
                'quantidade': orcamento.quantidade,
                'comprimento': orcamento.comprimento,
                'largura': orcamento.largura,
                'instalacao': orcamento.instalacao,
                'instalacao_valor': orcamento.instalacao_valor,  # 🔥 NOVO
                'rt_percentual': orcamento.rt_percentual,  # 🔥 NOVO
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
        print(f"❌ Erro em /orcamentos/json: {str(e)}")
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
        # Obter dados JSON da requisição
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "Nenhum dado JSON recebido"}), 400
        
        desenho_data = data.get('drawingAreaHTML')
        
        if not desenho_data:
            return jsonify({"success": False, "error": "Dados do desenho não fornecidos"}), 400
        
        print(f"💾 Salvando desenho para orçamento: {codigo}")
        
        # Verificar se o orçamento salvo existe
        orcamento_salvo = OrcamentoSalvo.query.filter_by(codigo=codigo).first()
        if not orcamento_salvo:
            return jsonify({"success": False, "error": "Orçamento salvo não encontrado"}), 404
        
        # Salvar na tabela DesenhoOrdemServico
        desenho_existente = DesenhoOrdemServico.query.filter_by(orcamento_salvo_codigo=codigo).first()
        
        if desenho_existente:
            # Atualizar desenho existente
            desenho_existente.desenho_data = desenho_data
            desenho_existente.data_criacao = datetime.utcnow()
            print("📝 Desenho existente atualizado na tabela DesenhoOrdemServico")
        else:
            # Criar novo registro de desenho
            novo_desenho = DesenhoOrdemServico(
                orcamento_salvo_codigo=codigo,
                desenho_data=desenho_data
            )
            db.session.add(novo_desenho)
            print("🆕 Novo desenho criado na tabela DesenhoOrdemServico")
        
        # Também salvar no campo desenho_ordem_servico do OrcamentoSalvo
        orcamento_salvo.desenho_ordem_servico = desenho_data
        print("📝 Desenho salvo no campo desenho_ordem_servico do OrcamentoSalvo")
        
        db.session.commit()
        print("✅ Desenho salvo com sucesso no banco de dados")
        
        return jsonify({"success": True, "message": "Desenho salvo com sucesso"})
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Erro ao salvar desenho: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/detalhes_ordem_servico/<codigo>')
def detalhes_ordem_servico(codigo):
    # 🔥 VERIFICAÇÃO DE LOGIN - IMPEDIR ACESSO SEM LOGIN
    if 'user_cpf' not in session:
        flash("Você precisa fazer login para acessar esta página.", "error")
        return redirect(url_for('login'))

    # 🔥 OBTER DADOS DO USUÁRIO LOGADO
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
    
    # 🔥 VERIFICAÇÃO DE PERMISSÃO - USUÁRIO PODE VER ESTA ORDEM?
    cliente = orcamentos[0].cliente
    
    # Admin pode ver tudo, usuário comum só vê seus próprios clientes
    if not is_admin and cliente.dono != user_cpf:
        flash("Você não tem permissão para acessar esta ordem de serviço.", "error")
        return redirect(url_for('ordens_servico'))

    # 🔥 AGRUPAR POR MATERIAL (SUA LÓGICA ORIGINAL)
    materiais_agrupados = {}
    for orcamento in orcamentos:
        material_nome = orcamento.material.nome
        
        if material_nome not in materiais_agrupados:
            materiais_agrupados[material_nome] = []
        
        materiais_agrupados[material_nome].append(orcamento)

    logo_url = "https://orcamento-t9w2.onrender.com/static/logo.jpg"
    
    usuario = Usuario.query.filter_by(cpf=user_cpf).first()
    telefone_usuario = usuario.telefone if usuario else ""

    # 🔥 CARREGAR DESENHO SALVO
    desenho_salvo = None
    desenho_registro = DesenhoOrdemServico.query.filter_by(
        orcamento_salvo_codigo=codigo
    ).order_by(DesenhoOrdemServico.data_criacao.desc()).first()
    
    if desenho_registro:
        desenho_salvo = desenho_registro.desenho_data
    elif orcamento_salvo.desenho_ordem_servico:
        desenho_salvo = orcamento_salvo.desenho_ordem_servico

    # 🔥 RENDERIZAR TEMPLATE COM TODOS OS DADOS
    return render_template(
        "detalhes_ordem_servico.html",
        logo_url=logo_url,
        codigo_orcamento=orcamento_salvo.codigo,
        data_salvo=orcamento_salvo.data_salvo,
        cliente_nome=orcamentos[0].cliente.nome if orcamentos else "Desconhecido",
        orcamentos=orcamentos,
        materiais_agrupados=materiais_agrupados,
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
        print(f"💰 Valor total atualizado: R$ {novo_valor_total:.2f}")
        print(f"📋 IDs restantes: {orcamento_ids_atualizados}")
        
        # 🔥 Redirecionar com mensagem de sucesso
        flash("Item removido do orçamento salvo com sucesso!", "success")
        return redirect(url_for('detalhes_orcamento_salvo', codigo=codigo, item_excluido='true'))
    
    except Exception as e:
        db.session.rollback()
        print(f"❌ Erro ao remover item: {str(e)}")
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



if __name__ == '__main__':
    criar_banco()
    app.run(debug=True)
