FROM mysql:8.4
# Generated schema contains DDL only; the image does not include private records.
# COPY sets readable permissions inside the image, avoiding bind-mount directory traversal failures.
COPY --chmod=0644 01-schema.sql /docker-entrypoint-initdb.d/01-schema.sql
