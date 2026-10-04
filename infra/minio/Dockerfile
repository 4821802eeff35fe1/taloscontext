FROM golang:1.24-bookworm AS build
ARG MINIO_VERSION=RELEASE.2025-10-15T17-29-55Z
RUN GOBIN=/out go install github.com/minio/minio@${MINIO_VERSION}
FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl && rm -rf /var/lib/apt/lists/*
COPY --from=build /out/minio /usr/local/bin/minio
RUN useradd --uid 10001 --create-home minio && mkdir /data && chown minio /data
USER minio
EXPOSE 9000 9001
ENTRYPOINT ["minio"]
