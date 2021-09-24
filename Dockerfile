FROM metricq/metricq-python:latest AS builder
LABEL maintainer="franz.hoepfner@tu-dresden.de"

USER root
RUN apt-get update && apt-get install -y git build-essential wget

USER metricq
COPY --chown=metricq:metricq . /home/metricq/wizard

WORKDIR /home/metricq/wizard
RUN . /home/metricq/venv/bin/activate && pip install -r requirements.txt
RUN . /home/metricq/venv/bin/activate && pip install gunicorn
WORKDIR /home/metricq
RUN wget -O wait-for-it.sh https://github.com/vishnubob/wait-for-it/raw/master/wait-for-it.sh && chmod +x wait-for-it.sh

FROM metricq/metricq-python:latest
LABEL maintainer="franz.hoepfner@tu-dresden.de"

USER metricq
COPY --from=builder --chown=metricq:metricq /home/metricq/venv /home/metricq/venv
COPY --from=builder --chown=metricq:metricq /home/metricq/wizard /home/metricq/wizard
COPY --from=builder --chown=metricq:metricq /home/metricq/wait-for-it.sh /home/metricq/
RUN mkdir /home/metricq/wizard/config-backup

WORKDIR /home/metricq/wizard

EXPOSE 8000

ARG wait_for_couchdb_url=127.0.0.1:5984
ENV wait_for_couchdb_url=$wait_for_couchdb_url

ARG couchdb_url=http://localhost:5984
ENV COUCHDB_URL=$couchdb_url

ARG couchdb_user=admin
ENV COUCHDB_USER=$couchdb_user

ARG couchdb_password=admin
ENV COUCHDB_PASSORD=$couchdb_password

ARG wait_for_rabbitmq_url=127.0.0.1:5672
ENV wait_for_rabbitmq_url=$wait_for_rabbitmq_url

ARG amqp_server=amqp://localhost:5672
ENV AMQP_SERVER=$amqp_server

VOLUME /home/metricq/wizard/config-backup/

CMD /home/metricq/wait-for-it.sh $wait_for_couchdb_url -- /home/metricq/wait-for-it.sh $wait_for_rabbitmq_url -- /home/metricq/venv/bin/gunicorn --bind=0.0.0.0:8000 --worker-class=aiohttp.GunicornWebWorker metricq_wizard_backend.main:create_app
