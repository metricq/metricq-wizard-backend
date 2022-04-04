metricq-wizard-backend
================

Your new web app is ready to go!

To run your app in development mode you'll need to:

1. Activate a python >=3.8 environment
2. Install the required packages with `pip install -e .[dev]`
3. Make sure the app's settings are configured correctly (see `app/settings.py`). You can also
 use environment variables to define sensitive settings, eg. DB connection variables
4. You can then run your app during development with `adev runserver -s static -v --debug-toolbar metricq_wizard_backend`

## Configuration

It is possible to override value in `metricq_wizard_backend/settings.py` by setting environment variables, for example:

```
amqp_server="amqp://admin:supersecretpassword@localhost/" adev runserver ...
```

One can also create an `.env` file in the repository root. For the parsing [python-dotenv](https://saurabh-kumar.com/python-dotenv/#usages) is used.

```dotenv
amqp_server="amqp://admin:supersecretpassword@localhost/"
dry_run=1
```
