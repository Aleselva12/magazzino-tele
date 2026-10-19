FROM python:3.13-slim
WORKDIR /app
RUN pip install --no-cache-dir flask==3.1.1 mysql-connector-python==9.3.0 gunicorn==23.0.0
RUN useradd -m -u 10001 tele
COPY --chmod=0644 app.py /app/app.py
RUN chmod 0755 /app && python -m py_compile /app/app.py
USER tele
EXPOSE 8082
CMD ["gunicorn","--bind","0.0.0.0:8082","--workers","2","app:app"]
