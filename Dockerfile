FROM python:3.12-slim

# Configuraciones para Python
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Instalar dependencias del sistema necesarias para psycopg (PostgreSQL) y herramientas de compilacion
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copiar e instalar los requerimientos
COPY requirements.txt /app/
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

# Copiar el codigo del proyecto
COPY . /app/

# Exponer el puerto
RUN python manage.py collectstatic --noinput

EXPOSE 8000

# Por defecto, ejecuta gunicorn apuntando al WSGI del config
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "config.wsgi:application"]

