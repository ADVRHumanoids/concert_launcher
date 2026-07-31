FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        coreutils \
        moreutils \
        openssh-server \
        procps \
        python3 \
        python3-psutil \
        tmux \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash tester \
    && echo "tester:integration-only" | chpasswd \
    && mkdir -p /run/sshd /home/tester/.ssh \
    && chown -R tester:tester /home/tester/.ssh \
    && chmod 700 /home/tester/.ssh

COPY tests/integration/ssh-host/entrypoint.sh /usr/local/bin/concert-test-sshd
COPY tests/integration/ssh-host/signal_receiver.py /usr/local/bin/concert-signal-receiver
RUN chmod +x /usr/local/bin/concert-test-sshd /usr/local/bin/concert-signal-receiver

EXPOSE 22

HEALTHCHECK --interval=1s --timeout=1s --retries=30 \
    CMD ssh-keyscan -T 1 localhost >/dev/null 2>&1 || exit 1

ENTRYPOINT ["/usr/local/bin/concert-test-sshd"]
