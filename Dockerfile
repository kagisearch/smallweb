FROM python:3.11-buster

ENV PYTHONUNBUFFERED=True
ENV URL_PREFIX=/smallweb
ENV MNT_DIR /app/data
ENV BUCKET kagi-us-central1-smallweb
ENV PORT 8080

RUN set -e; \
    apt-get update -y && apt-get install -y \
    libpq-dev \
    curl \
    gcc \
    tini \
    lsb-release \
    wget \
    fuse

RUN wget https://github.com/GoogleCloudPlatform/gcsfuse/releases/download/v1.2.0/gcsfuse_1.2.0_amd64.deb
RUN dpkg -i gcsfuse_1.2.0_amd64.deb
RUN apt-get clean

WORKDIR /app

COPY gcsfuse_run.sh gcsfuse_run.sh
RUN chmod +x gcsfuse_run.sh

COPY app/requirements.txt requirements.txt
RUN pip3 install -r requirements.txt

COPY app/ .
EXPOSE $PORT

ENTRYPOINT ["/usr/bin/tini", "--"]

CMD ["/app/gcsfuse_run.sh"]
