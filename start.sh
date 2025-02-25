#!/bin/sh

echo "Iniciando o aplicativo Flask no Gunicorn..."
gunicorn -b 0.0.0.0:5000 app:app
