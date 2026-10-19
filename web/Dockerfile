FROM python:3.13-slim
WORKDIR /app
RUN pip install --no-cache-dir flask==3.1.1 mysql-connector-python==9.3.0 gunicorn==23.0.0
COPY app.py /app/app.py
RUN useradd -m -u 10001 tele
USER tele
CMD ["gunicorn","--bind","0.0.0.0:8082","--workers","2","app:app"]
