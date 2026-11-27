FROM python:3.12-slim
WORKDIR /srv/central
RUN --mount=type=cache,target=/root/.cache/pip PIP_DEFAULT_TIMEOUT=180 pip install 'pip>=25.2,<27'
COPY pyproject.toml ./
COPY app ./app
RUN --mount=type=cache,target=/root/.cache/pip PIP_DEFAULT_TIMEOUT=180 pip install .
COPY alembic.ini ./
COPY migrations ./migrations
USER nobody
EXPOSE 8000
CMD ["gunicorn", "--threads=32", "--bind=0.0.0.0:8000", "app:create_app()"]
