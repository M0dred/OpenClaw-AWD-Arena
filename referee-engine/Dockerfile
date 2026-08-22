FROM python:3.9-slim

WORKDIR /app

# 安装必要的系统依赖
RUN unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy; \
    apt-get -o Acquire::http::Proxy=false -o Acquire::https::Proxy=false update && \
    apt-get -o Acquire::http::Proxy=false -o Acquire::https::Proxy=false install -y --no-install-recommends \
    curl \
    openssh-client \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

ARG TZ=UTC
ENV TZ=${TZ}

# 安装 docker cli
RUN unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy; \
    ARCH=$(uname -m) && \
    if [ "$ARCH" = "x86_64" ]; then \
        DOCKER_URL="https://download.docker.com/linux/static/stable/x86_64/docker-29.0.1.tgz"; \
    else \
        DOCKER_URL="https://download.docker.com/linux/static/stable/aarch64/docker-29.0.1.tgz"; \
    fi && \
    curl --noproxy '*' -fsSL $DOCKER_URL | tar xz -C /tmp/ && \
    mv /tmp/docker/docker /usr/local/bin/ && \
    rm -rf /tmp/docker

COPY requirements.txt .

RUN unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy; \
    pip install --no-cache-dir -r requirements.txt

COPY . .

# 暴露端口
EXPOSE 8000

# 启动命令
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
