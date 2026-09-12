FROM python:3.13-slim-bookworm@sha256:ed86c82274b3c69b52fb5820f358f0bd7df0b603332063cb5c6e32bd220c3e6e
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 ADDARR_DATA_DIR=/config
WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --require-hashes -r requirements.txt && groupadd --gid 1000 addarr && useradd --uid 1000 --gid 1000 --no-create-home addarr && mkdir /config && chown 1000:1000 /config
COPY addarr /app/addarr
ARG ADDARR_REVISION=unknown
ENV ADDARR_REVISION=${ADDARR_REVISION}
LABEL org.opencontainers.image.revision=${ADDARR_REVISION} io.addarr.updater.protocol="1"
USER 1000:1000
VOLUME ["/config"]
EXPOSE 8090
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8090/health/ready',timeout=3)"
STOPSIGNAL SIGTERM
ENTRYPOINT ["python", "-m", "addarr.cli"]
CMD ["serve"]
