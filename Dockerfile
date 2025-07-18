FROM python:3.11-bookworm

ENV PYTHONUNBUFFERED=True
ENV URL_PREFIX=/smallweb
ENV MNT_DIR /app/data
ENV BUCKET kagi-us-central1-smallweb
ENV PORT 8080

RUN set -e; \
    apt-get update -y && apt-get install --no-install-recommends -y \
    libpq-dev \
    curl \
    gcc \
    tini \
    lsb-release \
    wget \
    fuse && \
    wget https://github.com/GoogleCloudPlatform/gcsfuse/releases/download/v1.2.0/gcsfuse_1.2.0_amd64.deb && \
    dpkg -i gcsfuse_1.2.0_amd64.deb && \
    rm -rf gcsfuse_1.2.0_amd64.deb /var/lib/apt/lists/*

WORKDIR /app

COPY gcsfuse_run.sh gcsfuse_run.sh
RUN chmod +x gcsfuse_run.sh

COPY app/requirements.txt requirements.txt
RUN pip3 install --no-cache-dir -r requirements.txt

COPY smallweb.txt smallweb.txt

COPY app/ .
EXPOSE $PORT

ENTRYPOINT ["/usr/bin/tini", "--"]

CMD ["/app/gcsfuse_run.sh"]
