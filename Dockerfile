FROM metricq-python:latest AS builder
LABEL maintainer="franz.hoepfner@tu-dresden.de"

USER root
RUN apt-get update && apt-get install -y git

USER metricq
COPY --chown=metricq:metricq . /home/metricq/wizard

WORKDIR /home/metricq/wizard
RUN . /home/metricq/venv/bin/activate && pip install -r requirements.txt
RUN . /home/metricq/venv/bin/activate && pip install gunicorn

FROM metricq-python:latest
LABEL maintainer="franz.hoepfner@tu-dresden.de"

USER metricq
COPY --from=builder --chown=metricq:metricq /home/metricq/venv /home/metricq/venv
COPY --from=builder --chown=metricq:metricq /home/metricq/wizard /home/metricq/wizard

WORKDIR /home/metricq/wizard

EXPOSE 8000

ARG couchdb_url=http://localhost:5984
ENV COUCHDB_URL=$couchdb_url

ARG couchdb_user=admin
ENV COUCHDB_USER=$couchdb_user

ARG couchdb_pw=admin
ENV COUCHDB_PW=$couchdb_pw

ARG amqp_server=amqp://localhost:5672
ENV AMQP_SERVER=$amqp_server

CMD [ "/home/metricq/venv/bin/gunicorn", "--bind=0.0.0.0:8000", "--worker-class=aiohttp.GunicornWebWorker", "app.main:create_app" ]
