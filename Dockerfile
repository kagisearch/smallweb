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
    lsb-release; \
    gcsFuseRepo=gcsfuse-`lsb_release -c -s`; \
    echo "deb http://packages.cloud.google.com/apt $gcsFuseRepo main" | \
    tee /etc/apt/sources.list.d/gcsfuse.list; \
    curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | \
    apt-key add -; \
    apt-get update -y

RUN apt-get install -y gcsfuse
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
