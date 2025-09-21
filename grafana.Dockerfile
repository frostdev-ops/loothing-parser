FROM grafana/grafana:latest

# Copy provisioning files into the image
COPY monitoring/grafana/provisioning /etc/grafana/provisioning

# Ensure correct permissions
USER root
RUN chown -R grafana:grafana /etc/grafana/provisioning
USER grafana

# The entrypoint and cmd are inherited from the base image