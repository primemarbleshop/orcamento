import os

class Config:
    """Classe para armazenar as configurações do aplicativo Flask."""
    
    DATABASE_PATH = "/data/orcamentos.db"
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{DATABASE_PATH}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config['SECRET_KEY'] = '*Henrycm051094'
