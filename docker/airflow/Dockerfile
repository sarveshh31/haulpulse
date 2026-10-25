FROM apache/airflow:2.10.5-python3.11

# Airflow 2.x pins SQLAlchemy 1.4; our pipeline needs 2.x.
# So the pipeline gets its own virtualenv and Airflow just schedules it.
COPY --chown=airflow:root requirements.txt /tmp/requirements.txt

RUN python -m venv /home/airflow/pipeline-venv \
    && /home/airflow/pipeline-venv/bin/pip install --no-cache-dir --upgrade pip \
    && /home/airflow/pipeline-venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt