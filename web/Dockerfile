FROM python:3.13-slim
WORKDIR /app
RUN pip install --no-cache-dir flask==3.1.1 mysql-connector-python==9.3.0 gunicorn==23.0.0 openpyxl==3.1.5 xlrd==2.0.2
RUN useradd -m -u 10001 tele
COPY --chmod=0644 *.py /app/
RUN chmod 0755 /app && install -d -o tele -g tele -m 0700 /private-backups && python -m compileall -q /app
USER tele
EXPOSE 8082
CMD ["gunicorn","--bind","0.0.0.0:8082","--workers","2","--timeout","180","app:app"]
