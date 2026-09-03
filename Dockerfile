FROM python:3.14-slim

ENV PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg curl iputils-ping mtr-tiny \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv

COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv \
    && uv sync --frozen --no-dev

COPY . .

ENV PATH="/srv/.venv/bin:$PATH"

CMD ["python", "-m", "app.main"]
