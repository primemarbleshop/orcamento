from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class Usuario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    cpf = db.Column(db.String(14), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    senha = db.Column(db.String(128), nullable=False)
    admin = db.Column(db.Boolean, default=False)  # Indica se o usuário é admin

class Orcamento(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('cliente.id'), nullable=False)
    tipo_produto = db.Column(db.String, nullable=False)
    material_id = db.Column(db.Integer, db.ForeignKey('material.id'), nullable=False)
    quantidade = db.Column(db.Integer, nullable=False)
    valor_total = db.Column(db.Float, nullable=False)
    modelo_cuba = db.Column(db.String(50))

    # Novo campo: vincula um orçamento individual a um orçamento salvo
    orcamento_salvo_id = db.Column(db.Integer, db.ForeignKey('orcamento_salvo.id'), nullable=True)

    cliente = db.relationship('Cliente', backref=db.backref('orcamentos', lazy=True))
    material = db.relationship('Material', backref=db.backref('orcamentos', lazy=True))
    
    # Relacionamento com Orçamento Salvo (opcional)
    orcamento_salvo = db.relationship('OrcamentoSalvo', backref=db.backref('orcamentos', lazy=True))



class OrcamentoSalvo(db.Model):
    __tablename__ = "orcamento_salvo"
    
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(10), unique=True, nullable=False)
    data_salvo = db.Column(db.DateTime, default=db.func.current_timestamp())
    orcamento_id = db.Column(db.Integer, db.ForeignKey('orcamento.id'), nullable=False)
    orcamento = db.relationship('Orcamento', backref=db.backref('salvo', lazy=True))
