FROM python:3.12 AS build
RUN pip install uv
ENV UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PYTHON=python3.12 
WORKDIR /app
COPY pyproject.toml .
COPY uv.lock .
COPY README.md .
COPY src/ .
RUN  uv sync --locked && uv venv

######

FROM python:3.12
ENV PATH=/app/.venv/bin:$PATH
RUN  groupadd -r app &&  useradd -r -d /app -g app -N app
COPY --from=build --chown=app:app /app /app
COPY --chown=app:app entrypoint.sh /app/entrypoint.sh
USER app
ENTRYPOINT ["/app/entrypoint.sh"]
