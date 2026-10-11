FROM python:3.13.16-slim-trixie@sha256:70729b46c69b4f1e97c4822c1af3df53a1476cf5ddc6c087c0c10bc3a5678c2f AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    EBOOK_DATA_DIR=/app/data

WORKDIR /app

RUN apt-get update \
    && apt-get upgrade --yes \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --system myebooks && useradd --system --gid myebooks --home-dir /app myebooks

COPY pyproject.toml constraints.txt README.md LICENSE ./
COPY src ./src
RUN python -m pip install --no-cache-dir --upgrade --constraint constraints.txt setuptools msgpack urllib3 \
    && python -m pip install --no-cache-dir --constraint constraints.txt . \
    && python -m pip check

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
