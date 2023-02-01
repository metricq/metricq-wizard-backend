FROM metricq/metricq-python:v4.2 AS builder
LABEL maintainer="franz.hoepfner@tu-dresden.de"

USER root
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y \
    git \
    wget \
    build-essential \
    rustc \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/* 

USER metricq
COPY --chown=metricq:metricq . /home/metricq/wizard

WORKDIR /home/metricq/wizard
RUN pip install --user . gunicorn \
    ./metricq-wizard-plugin-source-bacnet \
    ./metricq-wizard-plugin-source-http \
    ./metricq-wizard-plugin-source-lmgd 

WORKDIR /home/metricq
RUN wget -O wait-for-it.sh https://github.com/vishnubob/wait-for-it/raw/master/wait-for-it.sh && chmod +x wait-for-it.sh

FROM metricq/metricq-python:v4.2
LABEL maintainer="franz.hoepfner@tu-dresden.de"

RUN mkdir -p /home/metricq/wizard/config-backup
COPY --from=builder --chown=metricq:metricq /home/metricq/.local /home/metricq/.local
COPY --from=builder --chown=metricq:metricq /home/metricq/wizard/api_doc /home/metricq/wizard/api_doc
COPY --from=builder --chown=metricq:metricq /home/metricq/wait-for-it.sh /home/metricq/

WORKDIR /home/metricq/wizard

EXPOSE 8000

ARG couchdb_url=http://admin:admin@localhost:5984
ENV COUCHDB_URL=$couchdb_url

ARG rabbitmq_url=amqp://admin:admin@localhost:5672
ENV RABBITMQ_URL=$rabbitmq_url

ARG rabbitmq_api_url=http://admin:admin@localhost:15672/api
ENV RABBITMQ_API_URL=$rabbitmq_api_url

ARG rabbitmq_data_host=/
ENV RABBITMQ_DATA_HOST=$rabbitmq_data_host

VOLUME /home/metricq/wizard/config-backup/

CMD /home/metricq/.local/bin/gunicorn --bind=0.0.0.0:8000 --worker-class=aiohttp.GunicornWebWorker metricq_wizard_backend.main:create_app
