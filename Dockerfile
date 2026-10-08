# fairscape-lite in one container: the API, the built UI, and a /data
# directory holding the index and uploaded crates. Without a volume on
# /data, everything uploaded goes away with the container.
#
#   docker build -t fairscape-lite .
#   docker run -p 8000:8000 fairscape-lite                    # throwaway
#   docker run -p 8000:8000 -v lite-data:/data fairscape-lite # kept

FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .
COPY --from=web /web/dist ./web/dist

RUN useradd --create-home lite && mkdir /data && chown lite /data
USER lite

# FAIRSCAPE_LITE_ROOT confines POST /rocrate path registration to /data,
# since a container port is rarely localhost-only. Uploads land there too.
ENV FAIRSCAPE_LITE_DB=/data/fairscape.db \
    FAIRSCAPE_LITE_UPLOADS=/data/uploads \
    FAIRSCAPE_LITE_ROOT=/data \
    FAIRSCAPE_LITE_UI=/app/web/dist

EXPOSE 8000
CMD ["uvicorn", "fairscape_lite.app:app", "--host", "0.0.0.0", "--port", "8000"]
