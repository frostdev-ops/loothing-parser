FROM prom/prometheus:latest

# Copy the config file directly into the image
COPY ./monitoring/prometheus.yml /etc/prometheus/prometheus.yml