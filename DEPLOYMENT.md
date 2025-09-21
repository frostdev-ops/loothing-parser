# WoW Combat Log Parser - Deployment Guide

## 📋 Table of Contents
- [Quick Start](#quick-start)
- [System Requirements](#system-requirements)
- [Installation Methods](#installation-methods)
- [Configuration](#configuration)
- [Production Deployment](#production-deployment)
- [Monitoring & Maintenance](#monitoring--maintenance)
- [Troubleshooting](#troubleshooting)
- [API Documentation](#api-documentation)

## 🚀 Quick Start

### One-Line Installation
```bash
curl -sSL https://raw.githubusercontent.com/your-repo/wow-log-parser/main/install.sh | bash
```

### Interactive Installation
```bash
chmod +x install.sh
./install.sh
```

The installation wizard will guide you through:
- System requirement checks
- Port configuration
- Directory setup
- Docker container deployment
- CLI tool installation

## 💻 System Requirements

### Minimum Requirements
- **OS**: Linux (Ubuntu 20.04+, Debian 10+, RHEL 8+, or compatible)
- **CPU**: 2 cores
- **RAM**: 2GB
- **Storage**: 10GB free space
- **Docker**: 20.10+ with Docker Compose
- **Python**: 3.9+ (optional, for CLI)

### Recommended Production Specs
- **CPU**: 4+ cores
- **RAM**: 8GB
- **Storage**: 50GB SSD
- **Network**: 100Mbps+

## 🔧 Installation Methods

### Method 1: Automated Installation (Recommended)
```bash
# Run the installation wizard
./install.sh

# The wizard will:
# 1. Check system requirements
# 2. Configure ports and directories
# 3. Build Docker images
# 4. Start services
# 5. Install CLI tool (optional)
```

### Method 2: Manual Docker Setup
```bash
# 1. Copy and configure environment
cp .env.example .env
# Edit .env with your settings

# 2. Build images
docker build -t wow-log-parser:latest .

# 3. Start services
docker-compose up -d

# 4. Verify deployment
curl http://localhost:8000/health
```

### Method 3: Docker Compose Production
```bash
# Use production configuration
cp .env.production .env
# Edit .env with production values

# Deploy with production stack
docker-compose -f docker-compose.prod.yml up -d
```

### Method 4: Kubernetes Deployment
```yaml
# See kubernetes/ directory for Helm charts
helm install wow-parser ./kubernetes/helm-chart \
  --namespace wow-parser \
  --create-namespace \
  --values ./kubernetes/values.yaml
```

## ⚙️ Configuration

### Essential Environment Variables
```bash
# API Configuration
API_KEY=your-secure-api-key-here  # Generate: openssl rand -hex 32
API_PORT=8000

# Database
DB_PATH=/app/data/combat_logs.db

# Web Interface
NGINX_PORT=80

# Monitoring (optional)
GRAFANA_PORT=3000
GRAFANA_PASSWORD=secure-password
```

### Configuration Files

#### nginx.conf
- Located at `./nginx.conf`
- Handles reverse proxy, SSL, and static files
- Customize for your domain and SSL certificates

#### docker-compose.yml
- Main service orchestration
- Includes API, nginx, and optional monitoring

#### .env
- Environment-specific configuration
- Never commit to version control
- Use `.env.example` as template

## 🏭 Production Deployment

### Pre-Deployment Checklist
- [ ] Generate secure API key
- [ ] Configure SSL certificates
- [ ] Set up domain name
- [ ] Configure firewall rules
- [ ] Set up monitoring
- [ ] Configure backups
- [ ] Review security settings

### Step-by-Step Production Setup

#### 1. Server Preparation
```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" \
  -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
```

#### 2. SSL/TLS Setup
```bash
# Using Let's Encrypt
sudo apt install certbot
sudo certbot certonly --standalone -d your-domain.com

# Update .env
ENABLE_SSL=true
SSL_CERT=/etc/letsencrypt/live/your-domain.com/fullchain.pem
SSL_KEY=/etc/letsencrypt/live/your-domain.com/privkey.pem
```

#### 3. Deploy Application
```bash
# Clone repository
git clone https://github.com/your-repo/wow-log-parser.git
cd wow-log-parser

# Configure for production
cp .env.production .env
# Edit .env with your values
nano .env

# Deploy
docker-compose -f docker-compose.prod.yml up -d

# Enable monitoring stack
docker-compose -f docker-compose.prod.yml --profile monitoring up -d
```

#### 4. Configure Firewall
```bash
# Allow required ports
sudo ufw allow 80/tcp   # HTTP
sudo ufw allow 443/tcp  # HTTPS
sudo ufw allow 3000/tcp # Grafana (restrict to admin IPs)
sudo ufw enable
```

#### 5. Set Up Reverse Proxy (Optional)
```nginx
# /etc/nginx/sites-available/wow-parser
server {
    listen 80;
    server_name parser.your-domain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name parser.your-domain.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## 📊 Monitoring & Maintenance

### Grafana Dashboards
Access at `http://your-domain:3000`
- Default login: admin / [your-configured-password]
- Pre-configured dashboards for:
  - API performance metrics
  - Log processing statistics
  - System resource usage
  - Error tracking

### Health Checks
```bash
# API health
curl http://localhost:8000/health

# Container status
docker-compose ps

# View logs
docker-compose logs -f api
```

### Database Backups
Automatic daily backups are configured by default:
```bash
# Manual backup
docker exec wow-log-parser-api \
  sqlite3 /app/data/combat_logs.db ".backup /app/data/backups/manual_$(date +%Y%m%d).db"

# Restore backup
docker exec wow-log-parser-api \
  sqlite3 /app/data/combat_logs.db ".restore /app/data/backups/backup.db"
```

### Log Management
```bash
# View application logs
docker-compose logs -f --tail=100 api

# Rotate logs
docker-compose exec api logrotate -f /etc/logrotate.conf

# Archive old logs
tar -czf logs_$(date +%Y%m%d).tar.gz ./logs/
```

### Updates & Upgrades
```bash
# Pull latest changes
git pull origin main

# Rebuild and restart
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

## 🔍 Troubleshooting

### Common Issues

#### Container Won't Start
```bash
# Check logs
docker-compose logs api

# Check permissions
ls -la ./data ./logs

# Fix permissions
sudo chown -R $(id -u):$(id -g) ./data ./logs
```

#### Database Locked Error
```bash
# Stop services
docker-compose down

# Remove lock file
rm ./data/combat_logs.db-wal
rm ./data/combat_logs.db-shm

# Restart
docker-compose up -d
```

#### High Memory Usage
```bash
# Check memory
docker stats

# Restart with limits
docker-compose down
docker-compose up -d --scale api=1
```

#### API Connection Refused
```bash
# Check if running
docker ps | grep wow-log-parser

# Check port binding
netstat -tulpn | grep 8000

# Check firewall
sudo ufw status
```

### Debug Mode
```bash
# Enable debug logging
echo "LOG_LEVEL=debug" >> .env
docker-compose restart api

# View debug logs
docker-compose logs -f api | grep DEBUG
```

## 📚 API Documentation

### Interactive Documentation
- Swagger UI: `http://your-domain:8000/docs`
- ReDoc: `http://your-domain:8000/redoc`

### Authentication
All API requests require the `X-API-Key` header:
```bash
curl -H "X-API-Key: your-api-key" http://localhost:8000/api/v1/logs
```

### Key Endpoints

#### Upload Log
```bash
curl -X POST http://localhost:8000/api/v1/logs/upload \
  -H "X-API-Key: your-api-key" \
  -F "file=@WoWCombatLog.txt"
```

#### Get Parse Status
```bash
curl http://localhost:8000/api/v1/logs/{log_id}/status \
  -H "X-API-Key: your-api-key"
```

#### Export Data
```bash
curl http://localhost:8000/api/v1/logs/{log_id}/export?format=json \
  -H "X-API-Key: your-api-key" \
  -o export.json
```

### WebSocket Streaming
```javascript
const ws = new WebSocket('ws://localhost:8000/ws');
ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    console.log('Parse progress:', data.progress);
};
```

## 🔐 Security Best Practices

1. **Always use HTTPS in production**
2. **Rotate API keys regularly**
3. **Restrict Grafana access to admin IPs**
4. **Keep Docker images updated**
5. **Enable rate limiting**
6. **Use read-only volume mounts where possible**
7. **Implement proper CORS policies**
8. **Regular security audits**

## 📞 Support

- **Documentation**: [Full Docs](./docs/)
- **Issues**: [GitHub Issues](https://github.com/your-repo/issues)
- **Discord**: [Community Server](https://discord.gg/your-server)

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.