FROM debian:bookworm-slim AS libredwg-builder

ARG LIBREDWG_VERSION=0.14
ARG LIBREDWG_SHA256=62ebb73b984f865960f20ed26619ea5f8789d5e3fd088fa40a2598384da81275

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential ca-certificates curl pkg-config python3 xz-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
RUN curl -fsSL \
        "https://github.com/LibreDWG/libredwg/releases/download/${LIBREDWG_VERSION}/libredwg-${LIBREDWG_VERSION}.tar.xz" \
        -o libredwg.tar.xz \
    && echo "${LIBREDWG_SHA256}  libredwg.tar.xz" | sha256sum -c - \
    && mkdir src \
    && tar -xJf libredwg.tar.xz -C src --strip-components=1 \
    && cd src \
    && ./configure \
        --prefix=/opt/libredwg \
        --disable-bindings \
        --disable-docs \
        --disable-shared \
    && make -j2 \
    && make install

FROM python:3.12-slim

COPY --from=libredwg-builder /opt/libredwg/bin/dwg2dxf /usr/local/bin/dwg2dxf

WORKDIR /app
COPY pyproject.toml README.md ./
COPY app ./app
RUN pip install --no-cache-dir .

EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]

