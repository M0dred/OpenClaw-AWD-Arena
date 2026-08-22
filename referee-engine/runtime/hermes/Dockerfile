FROM nousresearch/hermes-agent:latest

ARG TZ=UTC
ENV TZ=${TZ}

RUN unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY && \
    apt-get update && \
    apt-get install -y --no-install-recommends openssh-client && \
    rm -rf /var/lib/apt/lists/* && \
    mkdir -p /opt/runtime/hermes

COPY openclaw_wrapper.py /opt/runtime/hermes/openclaw_wrapper.py
COPY openclaw /opt/runtime/hermes/openclaw

RUN chmod +x /opt/runtime/hermes/openclaw && \
    ln -sf /opt/runtime/hermes/openclaw /usr/local/bin/openclaw
