FROM python:3-slim AS builder
LABEL maintainer="franz.hoepfner@tu-dresden.de"

RUN useradd -m metricq
RUN pip install virtualenv
RUN apt-get update && apt-get install -y git protobuf-compiler

USER metricq
COPY --chown=metricq:metricq . /home/metricq/wizard

WORKDIR /home/metricq
RUN virtualenv venv

RUN git clone https://github.com/metricq/metricq metricq

WORKDIR /home/metricq/metricq
RUN git checkout experimental-management-baseclass
RUN . /home/metricq/venv/bin/activate && pip install .

WORKDIR /home/metricq/wizard
RUN . /home/metricq/venv/bin/activate && pip install -r requirements.txt
RUN . /home/metricq/venv/bin/activate && pip install gunicorn

FROM python:3-slim
LABEL maintainer="franz.hoepfner@tu-dresden.de"

RUN useradd -m metricq

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

CMD [ "/home/metricq/venv/bin/gunicorn", "--bind=127.0.0.1:8000", "--worker-class=aiohttp.GunicornWebWorker", "app.main:create_app" ]