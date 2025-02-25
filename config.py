import os

class Config:
    """Classe para armazenar as configurações do aplicativo Flask."""
    
    SECRET_KEY = os.getenv("SECRET_KEY", "*Henrycm051094")  # Usa variável de ambiente ou valor padrão
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Configuração do Banco de Dados (Persistência no Volume do Render)
    DATABASE_PATH = "/data/orcamentos.db"
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{DATABASE_PATH}"
