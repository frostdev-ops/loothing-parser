FROM grafana/grafana:latest

# Switch to root to copy files and set permissions
USER root

# Copy provisioning files into the image
COPY monitoring/grafana/provisioning /etc/grafana/provisioning

# Ensure correct permissions (grafana user has UID 472)
RUN chown -R 472:0 /etc/grafana/provisioning && \
    chmod -R 755 /etc/grafana/provisioning

# Switch back to grafana user
USER grafana

# The entrypoint and cmd are inherited from the base image