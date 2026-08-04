FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY tests/integration/ssh-proxy/proxy.py /usr/local/bin/concert-ssh-proxy
RUN chmod +x /usr/local/bin/concert-ssh-proxy

EXPOSE 22 8474

HEALTHCHECK --interval=1s --timeout=1s --retries=30 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8474/status', timeout=1).read()"

ENTRYPOINT ["python3", "/usr/local/bin/concert-ssh-proxy"]
