import os


class Config:
    """Configuracoes do aplicativo Flask."""

    SECRET_KEY = os.getenv("SECRET_KEY", "*Henrycm051094")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    LOCAL_DATABASE_PATH = os.path.join(BASE_DIR, "orcamentos.db")
    RENDER_DATABASE_PATH = "/data/orcamentos.db"

    # No Render usa o volume persistente; localmente usa o banco do projeto.
    DATABASE_PATH = os.getenv(
        "DATABASE_PATH",
        RENDER_DATABASE_PATH if os.getenv("RENDER") else LOCAL_DATABASE_PATH,
    )
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{DATABASE_PATH.replace(os.sep, '/')}",
    )
