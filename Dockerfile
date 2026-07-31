FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    EBOOK_DATA_DIR=/app/data

WORKDIR /app

RUN groupadd --system myebooks && useradd --system --gid myebooks --home-dir /app myebooks

COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir .

RUN mkdir -p /app/data/covers && chown -R myebooks:myebooks /app
USER myebooks

EXPOSE 8000
CMD ["python", "-m", "myebooks.main"]

FROM runtime AS scaleway

USER root
COPY --chown=myebooks:myebooks deploy/catalog/ /app/data/
RUN test -s /app/data/myebooks.sqlite3 \
    && test -s /app/data/manifest.json \
    && test -d /app/data/covers
USER myebooks
