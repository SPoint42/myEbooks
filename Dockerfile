FROM python:3.13.15-slim-trixie@sha256:ffb752e139c0a19692a43af8d8523b274222dd68eebad5d583b45c2201c6e30a AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    EBOOK_DATA_DIR=/app/data

WORKDIR /app

RUN groupadd --system myebooks && useradd --system --gid myebooks --home-dir /app myebooks

COPY pyproject.toml constraints.txt README.md LICENSE ./
COPY src ./src
RUN python -m pip install --no-cache-dir --upgrade --constraint constraints.txt setuptools msgpack \
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
