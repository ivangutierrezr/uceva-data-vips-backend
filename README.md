# UCEVA Data VIPS Backend

Bienvenido al Backend de UCEVA Data VIPS. Este es un sistema basado en **Django (Python)** diseñado para extraer, procesar y exponer los datos de producción científica de la Universidad Central del Valle del Cauca (UCEVA) desde la plataforma **Scienti (Minciencias)**.

---

## 🚀 Requisitos Previos

*   **Python**: 3.10 o superior
*   **Gestor de Paquetes**: `pip`
*   **Base de Datos**: PostgreSQL (Recomendado) o SQLite (Desarrollo)
*   **(Opcional)**: Docker y Docker Compose para despliegue contenerizado.

---

## 🛠️ Instalación y Configuración Local

1.  **Clonar el Repositorio**:
    ```bash
    git clone <URL_DEL_REPO>
    cd uceva-data-vips-backend
    ```

2.  **Crear Entorno Virtual**:
    ```bash
    python -m venv .venv
    # Windows
    .venv\Scripts\activate
    # Mac/Linux
    source .venv/bin/activate
    ```

3.  **Instalar Dependencias**:
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configurar Variables de Entorno (.env)**:
    Crea un archivo `.env` en la raíz (junto a `manage.py`) basado en `.env.example` (si existe) o con las siguientes variables:
    ```ini
    DEBUG=True
    SECRET_KEY=tu_clave_secreta_django
    # Config DB (Opcional, por defecto SQLite)
    DB_NAME=uceva_data
    DB_USER=postgres
    DB_PASSWORD=secret
    DB_HOST=localhost
    DB_PORT=5432
    ```

5.  **Aplicar Migraciones**:
    ```bash
    python manage.py migrate
    ```

6.  **Crear Superusuario (Opcional)**:
    ```bash
    python manage.py createsuperuser
    ```

---

## 🕷️ Ejecutar el Scraper (Sincronización)

Para ejecutar el proceso de extracción de datos manualmente:

```bash
python manage.py sync_scienti
```

Este comando:
1.  Conecta a Scienti (Minciencias).
2.  Itera sobre los grupos de investigación de la UCEVA.
3.  Descarga y procesa Artículos, Libros, Capítulos y Tesis.
4.  Guarda/Actualiza la base de datos local.
5.  Limpia duplicados automáticamente.

**Logs en Pantalla**: Verás el progreso detallado (Página X de Y, Grupos procesados, errores, etc).

---

## 📊 Enriquecimiento de Artículos (Categorización)

Una vez ejecutado el scraper, puedes cruzar los datos con fuentes externas (SCIMAGO, PUBINDEX) para categorizar los artículos.

1.  **Colocar Archivos**:
    Asegúrate de tener los archivos `.xlsx` o `.csv` en:
    *   `uceva-data-vips-backend/datasets/scimago/` (Nombrados por año: `2019.xlsx`, `2024.xlsx`)
    *   `uceva-data-vips-backend/datasets/publindex/`

2.  **Ejecutar Comando**:
    ```bash
    python manage.py enrich_articles
    ```
    Este comando buscará por ISSN y guardará la categoría histórica de cada artículo.

---

## ▶️ Ejecutar el Servidor

Para iniciar el servidor de desarrollo:

```bash
python manage.py runserver
```
El backend estará disponible en `http://127.0.0.1:8000/`.

---

## 🐳 Despliegue con Docker

El proyecto incluye un `docker-compose.yml` básico para orquestar la aplicación y la base de datos.
*(Asegúrate de tener Docker instalado)*

1.  **Construir y Levantar**:
    ```bash
    docker-compose up --build
    ```

2.  **Ejecutar Migraciones dentro del Contenedor**:
    ```bash
    docker-compose exec web python manage.py migrate
    ```

3.  **Ejecutar Scraper dentro del Contenedor**:
    ```bash
    docker-compose exec web python manage.py sync_scienti
    ```

---

## 📚 Estructura del Proyecto

*   `config/`: Configuración principal de Django (settings, urls, wsgi).
*   `scienti/`: App principal donde reside la lógica de negocio.
    *   `models.py`: Definición de tablas de la BD.
    *   `management/commands/sync_scienti.py`: **Lógica del Scraper**.
    *   `views.py`, `urls.py`: Endpoints para exponer datos.
*   `users/`: Gestión de usuarios y autenticación (si aplica).

---

## 🤝 Contribución

1.  Hacer Fork del repositorio.
2.  Crear rama (`git checkout -b feature/nueva-funcionalidad`).
3.  Commit (`git commit -m 'Añadir nueva funcionalidad'`).
4.  Push (`git push origin feature/nueva-funcionalidad`).
5.  Abrir Pull Request.

---
**UCEVA Data VIPS - 2026**
