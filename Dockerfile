# Usa uma imagem oficial do Python
FROM python:3.10

# Define o diretório de trabalho dentro do contêiner
WORKDIR /app

# Copia os arquivos do projeto para dentro do contêiner
COPY . /app

# Instala as dependências do Python
RUN pip install --no-cache-dir -r requirements.txt

# Cria a pasta onde o banco de dados será armazenado
RUN mkdir -p /data

# Expõe a porta 5000 para rodar o Flask
EXPOSE 5000

# Comando para rodar o aplicativo com Gunicorn
CMD ["gunicorn", "-b", "0.0.0.0:5000", "app:app"]
