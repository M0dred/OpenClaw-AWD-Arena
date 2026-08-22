FROM node:20-alpine

# 使用 Alpine 官方默认仓库，保证全球任何地区都能构建。
# 中国大陆用户如需加速，可在构建前手动替换仓库，例如：
#   docker build --build-arg APK_MIRROR=mirrors.aliyun.com ...
# 或在本地配置 Docker 镜像加速器，不要写死在 Dockerfile 中。
ARG APK_MIRROR=""
RUN if [ -n "$APK_MIRROR" ]; then \
        sed -i "s|dl-cdn.alpinelinux.org|${APK_MIRROR}|g" /etc/apk/repositories; \
    fi && \
    apk add --no-cache bash curl iputils sqlite python3 tzdata \
    supervisor openssh-server shadow busybox-suid

ARG TZ=UTC
ENV TZ=${TZ}
ENV MAINTENANCE_USERNAME=defender

RUN addgroup -S webops && \
    addgroup -S maintops && \
    addgroup -S appdb && \
    adduser -S -D -h /home/defender -s /bin/sh -G maintops defender && \
    adduser -S -D -h /home/webuser -s /sbin/nologin -G webops webuser && \
    addgroup webuser appdb && \
    ssh-keygen -A && \
    passwd -l root && \
    sed -i 's/#PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config && \
    sed -i 's/#PubkeyAuthentication.*/PubkeyAuthentication yes/' /etc/ssh/sshd_config && \
    sed -i 's/#PasswordAuthentication.*/PasswordAuthentication yes/' /etc/ssh/sshd_config && \
    printf '\nAllowUsers defender\nUsePAM no\n' >> /etc/ssh/sshd_config && \
    mkdir -p /run/sshd /var/log/supervisor /home/defender/.ssh /etc/crontabs

WORKDIR /app

COPY app.py /app/app.py
COPY entrypoint.sh /app/entrypoint.sh
COPY flag_sync.sh /app/flag_sync.sh
COPY supervisord.conf /etc/supervisord.conf

RUN chmod +x /app/entrypoint.sh && \
    chmod +x /app/flag_sync.sh && \
    mkdir -p /app/static/documents /app/static/backup /app/data /app/reports \
    /app/reports/templates /var/log/supervisor /opt/.credentials && \
    chown root:maintops /app && \
    chmod 775 /app && \
    chown defender:webops /app/app.py && \
    chmod 644 /app/app.py && \
    chown root:root /app/entrypoint.sh && \
    chmod 755 /app/entrypoint.sh && \
    chown root:root /app/static && \
    chmod 755 /app/static && \
    chown root:root /app/static/backup && \
    chmod 755 /app/static/backup && \
    chown root:root /app/static/documents && \
    chmod 755 /app/static/documents && \
    chown webuser:appdb /app/data && \
    chmod 700 /app/data && \
    chown defender:webops /app/reports && \
    chmod 770 /app/reports && \
    chown root:maintops /var/log/supervisor && \
    chmod 775 /var/log/supervisor && \
    chown root:root /opt/.credentials && \
    chmod 700 /opt/.credentials && \
    chown -R defender:maintops /home/defender && \
    chmod 700 /home/defender /home/defender/.ssh && \
    chown root:root /etc/crontabs && \
    chmod 600 /etc/crontabs

EXPOSE 3000 22

HEALTHCHECK --interval=10s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:3000/health || exit 1

ENTRYPOINT ["/app/entrypoint.sh"]
