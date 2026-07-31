FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends openssh-client \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace
COPY . /workspace

RUN pip install --no-cache-dir -e . pytest pytest-asyncio pytest-timeout

COPY tests/integration/runner/entrypoint.sh /usr/local/bin/concert-test-runner
RUN chmod +x /usr/local/bin/concert-test-runner

ENTRYPOINT ["/usr/local/bin/concert-test-runner"]
CMD ["pytest", "--timeout=60", "-m", "docker", "tests/integration", "-v"]
