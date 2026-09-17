# syntax=docker/dockerfile:1
ARG UVX_BUILDER=ghcr.io/aquaveo/tethys-uvx:builder-a3148d5
ARG UVX_RUNTIME=ghcr.io/aquaveo/tethys-uvx:runtime-base-a3148d5

FROM ${UVX_BUILDER} AS builder

ENV UV_CACHE_DIR=/cache/uv
ENV npm_config_cache=/cache/npm

WORKDIR ${TETHYS_HOME}

USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgdal-dev gdal-bin g++ \
    && rm -rf /var/lib/apt/lists/*
USER 1000:1000

COPY requirements/overrides.txt ${TETHYS_HOME}/overrides.txt
COPY . ${TETHYS_HOME}/apps/tethysapp-fimeval-gui

RUN --mount=type=cache,target=/cache/uv --mount=type=cache,target=/cache/npm \
    cd ${TETHYS_HOME}/apps/tethysapp-fimeval-gui/reactapp && npm install && npm run build && \
    cd ${TETHYS_HOME}/apps/tethysapp-fimeval-gui && \
    uv pip install . --overrides ${TETHYS_HOME}/overrides.txt && \
    uv pip install --overrides ${TETHYS_HOME}/overrides.txt "gdal==$(gdal-config --version)"

FROM ${UVX_RUNTIME}

USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends gdal-bin \
    && rm -rf /var/lib/apt/lists/*
USER 1000:1000

COPY --from=builder /opt/python /opt/python
COPY --from=builder /opt/conda /opt/conda
