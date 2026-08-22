FROM openclaw/ctf-target:test

ARG TZ=UTC
ENV TZ=${TZ}

# Copy custom web server with hidden debug endpoint
COPY awd_web_server.py /app/server.py

# Copy modified entrypoint
COPY awd_entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh
RUN mkdir -p /app/reports

# FLAG 5: Hidden environment variable for debug endpoint
ENV _INTERNAL_DEBUG_FLAG="FLAG{922de5cd0835f6aebe47419f5cecc064}"

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
