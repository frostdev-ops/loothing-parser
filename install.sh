#!/bin/bash

# ========================================================================
# WoW Combat Log Parser - Installation Wizard
# ========================================================================
# This script will help you install and configure the WoW Combat Log Parser
# It will:
# - Check system requirements
# - Configure ports and directories
# - Set up Docker containers
# - Create necessary configuration files
# - Install the CLI tool
# ========================================================================

set -e  # Exit on error

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color
BOLD='\033[1m'

# Default values
DEFAULT_API_PORT=8000
DEFAULT_NGINX_PORT=80
DEFAULT_GRAFANA_PORT=3000
DEFAULT_DATA_DIR="./data"
DEFAULT_LOGS_DIR="./logs"
DEFAULT_CONFIG_DIR="./config"

# ASCII Art Logo
print_logo() {
    echo -e "${CYAN}"
    cat << "EOF"
╔══════════════════════════════════════════════════════════════════╗
║                                                                  ║
║   ██╗    ██╗ ██████╗ ██╗    ██╗    ██╗      ██████╗  ██████╗   ║
║   ██║    ██║██╔═══██╗██║    ██║    ██║     ██╔═══██╗██╔════╝   ║
║   ██║ █╗ ██║██║   ██║██║ █╗ ██║    ██║     ██║   ██║██║  ███╗  ║
║   ██║███╗██║██║   ██║██║███╗██║    ██║     ██║   ██║██║   ██║  ║
║   ╚███╔███╔╝╚██████╔╝╚███╔███╔╝    ███████╗╚██████╔╝╚██████╔╝  ║
║    ╚══╝╚══╝  ╚═════╝  ╚══╝╚══╝     ╚══════╝ ╚═════╝  ╚═════╝   ║
║                                                                  ║
║                    Combat Log Parser v1.0                       ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
EOF
    echo -e "${NC}"
}

# Print section header
print_header() {
    echo -e "\n${BLUE}════════════════════════════════════════════════════════${NC}"
    echo -e "${BOLD}$1${NC}"
    echo -e "${BLUE}════════════════════════════════════════════════════════${NC}\n"
}

# Print success message
print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

# Print error message
print_error() {
    echo -e "${RED}✗${NC} $1"
}

# Print warning message
print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

# Print info message
print_info() {
    echo -e "${CYAN}ℹ${NC} $1"
}

# Prompt user for input with default value
prompt_with_default() {
    local prompt="$1"
    local default="$2"
    local var_name="$3"

    echo -ne "${BOLD}$prompt${NC} [${GREEN}$default${NC}]: "
    read -r user_input

    if [[ -z "$user_input" ]]; then
        eval "$var_name='$default'"
    else
        eval "$var_name='$user_input'"
    fi
}

# Check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check system requirements
check_requirements() {
    print_header "Checking System Requirements"

    local all_good=true

    # Check for Docker
    if command_exists docker; then
        print_success "Docker is installed ($(docker --version | cut -d' ' -f3 | cut -d',' -f1))"
    else
        print_error "Docker is not installed"
        echo "       Please install Docker: https://docs.docker.com/get-docker/"
        all_good=false
    fi

    # Check for Docker Compose
    if command_exists docker-compose || docker compose version >/dev/null 2>&1; then
        print_success "Docker Compose is installed"
    else
        print_error "Docker Compose is not installed"
        echo "       Please install Docker Compose: https://docs.docker.com/compose/install/"
        all_good=false
    fi

    # Check for Python 3
    if command_exists python3; then
        local python_version=$(python3 --version | cut -d' ' -f2)
        print_success "Python 3 is installed ($python_version)"
    else
        print_warning "Python 3 is not installed (optional for CLI)"
    fi

    # Check for Git
    if command_exists git; then
        print_success "Git is installed ($(git --version | cut -d' ' -f3))"
    else
        print_warning "Git is not installed (optional for updates)"
    fi

    # Check disk space (require at least 1GB free)
    local free_space=$(df -BG . | tail -1 | awk '{print $4}' | sed 's/G//')
    if [[ "$free_space" -gt 1 ]]; then
        print_success "Sufficient disk space available (${free_space}GB free)"
    else
        print_error "Insufficient disk space (${free_space}GB free, need at least 1GB)"
        all_good=false
    fi

    # Check current user ID for Docker permissions
    USER_ID=$(id -u)
    GROUP_ID=$(id -g)
    print_info "Current user: $(whoami) (UID: $USER_ID, GID: $GROUP_ID)"

    if [[ "$all_good" == false ]]; then
        echo
        print_error "Please install missing requirements before continuing"
        exit 1
    fi

    echo
    print_success "All system requirements met!"
}

# Configure installation settings
configure_installation() {
    print_header "Configuration Settings"

    echo -e "${BOLD}Let's configure your installation:${NC}\n"

    # Installation mode
    echo -e "${BOLD}Installation Mode:${NC}"
    echo "  1) Development (with hot-reload and debug features)"
    echo "  2) Production (optimized for performance)"
    echo
    prompt_with_default "Select mode (1-2)" "2" "install_mode"

    if [[ "$install_mode" == "1" ]]; then
        INSTALL_MODE="development"
        print_info "Development mode selected"
    else
        INSTALL_MODE="production"
        print_info "Production mode selected"
    fi

    echo

    # Port configuration
    echo -e "${BOLD}Port Configuration:${NC}"
    prompt_with_default "API Port" "$DEFAULT_API_PORT" "API_PORT"
    prompt_with_default "Web Interface Port" "$DEFAULT_NGINX_PORT" "NGINX_PORT"
    prompt_with_default "Grafana Dashboard Port" "$DEFAULT_GRAFANA_PORT" "GRAFANA_PORT"

    echo

    # Directory configuration
    echo -e "${BOLD}Directory Configuration:${NC}"
    prompt_with_default "Data directory" "$DEFAULT_DATA_DIR" "DATA_DIR"
    prompt_with_default "Logs directory" "$DEFAULT_LOGS_DIR" "LOGS_DIR"
    prompt_with_default "Config directory" "$DEFAULT_CONFIG_DIR" "CONFIG_DIR"

    echo

    # API Key generation
    echo -e "${BOLD}Security Configuration:${NC}"
    echo "Generate a secure API key for authentication?"
    prompt_with_default "Generate API key? (y/n)" "y" "generate_api_key"

    if [[ "$generate_api_key" == "y" ]] || [[ "$generate_api_key" == "Y" ]]; then
        API_KEY=$(openssl rand -hex 32 2>/dev/null || cat /dev/urandom | tr -dc 'a-zA-Z0-9' | fold -w 32 | head -n 1)
        print_success "Generated secure API key"
    else
        prompt_with_default "Enter your API key" "your-secure-api-key-here" "API_KEY"
    fi

    echo

    # Monitoring setup
    echo -e "${BOLD}Monitoring Configuration:${NC}"
    echo "Enable Grafana monitoring dashboards?"
    prompt_with_default "Enable monitoring? (y/n)" "y" "enable_monitoring"

    if [[ "$enable_monitoring" == "y" ]] || [[ "$enable_monitoring" == "Y" ]]; then
        ENABLE_MONITORING=true
        prompt_with_default "Grafana admin password" "admin" "GRAFANA_PASSWORD"
    else
        ENABLE_MONITORING=false
    fi

    echo

    # SSL/TLS configuration
    echo -e "${BOLD}SSL/TLS Configuration:${NC}"
    echo "Configure SSL/TLS for secure connections?"
    prompt_with_default "Enable SSL/TLS? (y/n)" "n" "enable_ssl"

    if [[ "$enable_ssl" == "y" ]] || [[ "$enable_ssl" == "Y" ]]; then
        ENABLE_SSL=true
        prompt_with_default "SSL certificate path" "./ssl/cert.pem" "SSL_CERT"
        prompt_with_default "SSL key path" "./ssl/key.pem" "SSL_KEY"
    else
        ENABLE_SSL=false
    fi
}

# Create directory structure
create_directories() {
    print_header "Creating Directory Structure"

    # Create main directories
    for dir in "$DATA_DIR" "$LOGS_DIR" "$CONFIG_DIR" "$DATA_DIR/uploads" "$DATA_DIR/exports"; do
        if [[ ! -d "$dir" ]]; then
            mkdir -p "$dir"
            print_success "Created directory: $dir"
        else
            print_info "Directory already exists: $dir"
        fi
    done

    # Set permissions
    chmod -R 755 "$DATA_DIR" "$LOGS_DIR" "$CONFIG_DIR"
    print_success "Set directory permissions"
}

# Generate configuration files
generate_configs() {
    print_header "Generating Configuration Files"

    # Generate .env file
    cat > .env << EOF
# ============================================
# WoW Combat Log Parser - Environment Config
# Generated: $(date)
# Mode: $INSTALL_MODE
# ============================================

# User/Group IDs
USER_ID=$USER_ID
GROUP_ID=$GROUP_ID

# Installation Mode
INSTALL_MODE=$INSTALL_MODE

# API Configuration
API_KEY=$API_KEY
API_PORT=$API_PORT

# Database Configuration
DB_PATH=/app/data/combat_logs.db

# Server Configuration
HOST=0.0.0.0
PORT=$API_PORT
LOG_LEVEL=$([ "$INSTALL_MODE" = "development" ] && echo "debug" || echo "info")

# Directory Configuration
DATA_DIR=$DATA_DIR
LOGS_DIR=$LOGS_DIR
CONFIG_DIR=$CONFIG_DIR

# Web Interface
NGINX_PORT=$NGINX_PORT

# Monitoring
ENABLE_MONITORING=$ENABLE_MONITORING
GRAFANA_PORT=$GRAFANA_PORT
GRAFANA_PASSWORD=$GRAFANA_PASSWORD

# SSL/TLS
ENABLE_SSL=$ENABLE_SSL
SSL_CERT=$SSL_CERT
SSL_KEY=$SSL_KEY

# Performance Settings
WORKERS=$([ "$INSTALL_MODE" = "development" ] && echo "1" || echo "4")
MAX_UPLOAD_SIZE=500M
REQUEST_TIMEOUT=300
EOF

    print_success "Generated .env configuration file"

    # Generate docker-compose.override.yml for customizations
    if [[ "$INSTALL_MODE" == "development" ]]; then
        cat > docker-compose.override.yml << EOF
# Development overrides
services:
  streaming-server:
    environment:
      - RELOAD=true
      - DEBUG=true
      - LOG_LEVEL=debug
    command: ["python", "-m", "src.api.streaming_server"]

  nginx:
    volumes:
      - ./static:/usr/share/nginx/html/static:ro
EOF
        print_success "Generated development override configuration"
    fi

    # Generate nginx configuration with custom ports
    if [[ "$ENABLE_SSL" == true ]]; then
        cat > nginx.conf << EOF
events {
    worker_connections 1024;
}

http {
    include /etc/nginx/mime.types;
    default_type application/octet-stream;

    client_max_body_size ${MAX_UPLOAD_SIZE:-500M};

    upstream streaming-server {
        server streaming-server:8000;
    }

    server {
        listen 80;
        server_name _;
        return 301 https://\$server_name\$request_uri;
    }

    server {
        listen 443 ssl http2;
        server_name _;

        ssl_certificate $SSL_CERT;
        ssl_certificate_key $SSL_KEY;
        ssl_protocols TLSv1.2 TLSv1.3;
        ssl_ciphers HIGH:!aNULL:!MD5;

        location / {
            root /usr/share/nginx/html;
            try_files \$uri \$uri/ /index.html;
        }

        location /api {
            proxy_pass http://streaming-server;
            proxy_set_header Host \$host;
            proxy_set_header X-Real-IP \$remote_addr;
            proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto \$scheme;
            proxy_read_timeout 300s;
            proxy_connect_timeout 75s;
        }

        location /ws {
            proxy_pass http://streaming-server;
            proxy_http_version 1.1;
            proxy_set_header Upgrade \$http_upgrade;
            proxy_set_header Connection "upgrade";
            proxy_set_header Host \$host;
            proxy_set_header X-Real-IP \$remote_addr;
            proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        }
    }
}
EOF
    else
        cat > nginx.conf << EOF
events {
    worker_connections 1024;
}

http {
    include /etc/nginx/mime.types;
    default_type application/octet-stream;

    client_max_body_size ${MAX_UPLOAD_SIZE:-500M};

    upstream streaming-server {
        server streaming-server:8000;
    }

    server {
        listen 80;
        server_name _;

        location / {
            root /usr/share/nginx/html;
            try_files \$uri \$uri/ /index.html;
        }

        location /api {
            proxy_pass http://streaming-server;
            proxy_set_header Host \$host;
            proxy_set_header X-Real-IP \$remote_addr;
            proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto \$scheme;
            proxy_read_timeout 300s;
            proxy_connect_timeout 75s;
        }

        location /ws {
            proxy_pass http://streaming-server;
            proxy_http_version 1.1;
            proxy_set_header Upgrade \$http_upgrade;
            proxy_set_header Connection "upgrade";
            proxy_set_header Host \$host;
            proxy_set_header X-Real-IP \$remote_addr;
            proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        }
    }
}
EOF
    fi

    print_success "Generated nginx configuration"
}

# Build Docker images
build_docker_images() {
    print_header "Building Docker Images"

    echo -e "${CYAN}This may take a few minutes...${NC}\n"

    # Build main application image
    print_info "Building application image..."
    if docker build -t wow-log-parser:latest . > /dev/null 2>&1; then
        print_success "Application image built successfully"
    else
        print_error "Failed to build application image"
        echo "       Run 'docker build -t wow-log-parser:latest .' to see detailed error"
        exit 1
    fi

    # Build nginx image if custom
    if [[ -f "nginx.Dockerfile" ]]; then
        print_info "Building nginx image..."
        if docker build -f nginx.Dockerfile -t wow-log-parser-nginx:latest . > /dev/null 2>&1; then
            print_success "Nginx image built successfully"
        else
            print_warning "Failed to build custom nginx image, will use default"
        fi
    fi
}

# Install CLI tool
install_cli() {
    print_header "Installing CLI Tool"

    echo "Install the command-line interface tool?"
    prompt_with_default "Install CLI? (y/n)" "y" "install_cli"

    if [[ "$install_cli" != "y" ]] && [[ "$install_cli" != "Y" ]]; then
        print_info "Skipping CLI installation"
        return
    fi

    # Check if Python 3 is available
    if ! command_exists python3; then
        print_warning "Python 3 is required for CLI installation"
        echo "       Install Python 3 and run: pip install -e ."
        return
    fi

    # Create virtual environment if it doesn't exist
    if [[ ! -d "venv" ]]; then
        print_info "Creating Python virtual environment..."
        python3 -m venv venv
        print_success "Virtual environment created"
    fi

    # Activate virtual environment and install
    print_info "Installing CLI tool..."
    source venv/bin/activate
    pip install --upgrade pip > /dev/null 2>&1
    pip install -e . > /dev/null 2>&1
    deactivate

    # Create system-wide CLI wrapper
    cat > wow-parser << 'EOF'
#!/bin/bash
# WoW Combat Log Parser CLI Wrapper

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

if [[ -f "venv/bin/activate" ]]; then
    source venv/bin/activate
    python -m src.cli "$@"
    deactivate
else
    echo "Error: Virtual environment not found"
    echo "Please run the install.sh script first"
    exit 1
fi
EOF

    chmod +x wow-parser
    print_success "CLI tool installed (./wow-parser)"

    # Offer to install globally
    echo
    echo "Install CLI globally (requires sudo)?"
    prompt_with_default "Install globally? (y/n)" "n" "install_global"

    if [[ "$install_global" == "y" ]] || [[ "$install_global" == "Y" ]]; then
        if sudo cp wow-parser /usr/local/bin/; then
            print_success "CLI installed globally as 'wow-parser'"
        else
            print_warning "Failed to install globally, use './wow-parser' locally"
        fi
    fi
}

# Start services
start_services() {
    print_header "Starting Services"

    echo -e "${CYAN}Starting Docker containers...${NC}\n"

    # Determine docker-compose command
    if command_exists docker-compose; then
        COMPOSE_CMD="docker-compose"
    else
        COMPOSE_CMD="docker compose"
    fi

    # Start services
    if [[ "$INSTALL_MODE" == "development" ]]; then
        print_info "Starting in development mode..."
        $COMPOSE_CMD up -d --build
    else
        print_info "Starting in production mode..."
        $COMPOSE_CMD -f docker-compose.yml up -d --build
    fi

    # Wait for services to be ready
    print_info "Waiting for services to be ready..."
    sleep 5

    # Check service status
    if docker ps | grep -q "wow-log-parser"; then
        print_success "Services started successfully"
    else
        print_error "Services failed to start"
        echo "       Check logs with: $COMPOSE_CMD logs"
        exit 1
    fi
}

# Display post-installation information
show_summary() {
    print_header "Installation Complete!"

    echo -e "${GREEN}${BOLD}WoW Combat Log Parser has been successfully installed!${NC}\n"

    echo -e "${BOLD}Service URLs:${NC}"
    echo -e "  ${CYAN}►${NC} Web Interface: http://localhost:${NGINX_PORT}"
    echo -e "  ${CYAN}►${NC} API Endpoint:  http://localhost:${API_PORT}/api/v1"
    echo -e "  ${CYAN}►${NC} API Docs:      http://localhost:${API_PORT}/docs"

    if [[ "$ENABLE_MONITORING" == true ]]; then
        echo -e "  ${CYAN}►${NC} Grafana:       http://localhost:${GRAFANA_PORT}"
        echo -e "                   (Username: admin, Password: ${GRAFANA_PASSWORD})"
    fi

    echo
    echo -e "${BOLD}API Authentication:${NC}"
    echo -e "  ${CYAN}►${NC} API Key: ${GREEN}${API_KEY}${NC}"
    echo -e "     ${YELLOW}Save this key securely - you'll need it for API access${NC}"

    echo
    echo -e "${BOLD}Quick Start Commands:${NC}"
    echo -e "  ${CYAN}►${NC} View logs:     ${COMPOSE_CMD} logs -f"
    echo -e "  ${CYAN}►${NC} Stop services: ${COMPOSE_CMD} down"
    echo -e "  ${CYAN}►${NC} Start services: ${COMPOSE_CMD} up -d"
    echo -e "  ${CYAN}►${NC} Parse a log:   ./wow-parser parse <logfile>"

    echo
    echo -e "${BOLD}Data Locations:${NC}"
    echo -e "  ${CYAN}►${NC} Database:      ${DATA_DIR}/combat_logs.db"
    echo -e "  ${CYAN}►${NC} Uploads:       ${DATA_DIR}/uploads/"
    echo -e "  ${CYAN}►${NC} Exports:       ${DATA_DIR}/exports/"
    echo -e "  ${CYAN}►${NC} Logs:          ${LOGS_DIR}/"

    echo
    echo -e "${BOLD}Next Steps:${NC}"
    echo -e "  1. Upload a combat log file via the web interface"
    echo -e "  2. View parsing results and statistics"
    echo -e "  3. Export data in various formats"

    if [[ "$ENABLE_MONITORING" == true ]]; then
        echo -e "  4. Configure Grafana dashboards for monitoring"
    fi

    echo
    echo -e "${BLUE}════════════════════════════════════════════════════════${NC}"
    echo -e "${BOLD}${GREEN}Thank you for installing WoW Combat Log Parser!${NC}"
    echo -e "${BLUE}════════════════════════════════════════════════════════${NC}"
}

# Create uninstall script
create_uninstall_script() {
    cat > uninstall.sh << 'EOF'
#!/bin/bash

# WoW Combat Log Parser - Uninstaller

echo "This will remove the WoW Combat Log Parser installation."
read -p "Are you sure? (y/N): " -n 1 -r
echo

if [[ $REPLY =~ ^[Yy]$ ]]; then
    # Stop and remove containers
    docker-compose down -v

    # Remove images
    docker rmi wow-log-parser:latest wow-log-parser-nginx:latest 2>/dev/null

    # Remove global CLI if installed
    sudo rm -f /usr/local/bin/wow-parser 2>/dev/null

    echo "Uninstallation complete."
    echo "Note: Data directories and configuration files were preserved."
    echo "To completely remove all data, manually delete:"
    echo "  - ./data/"
    echo "  - ./logs/"
    echo "  - ./config/"
    echo "  - .env"
else
    echo "Uninstallation cancelled."
fi
EOF
    chmod +x uninstall.sh
    print_info "Created uninstall.sh script"
}

# Main installation flow
main() {
    clear
    print_logo

    echo -e "${BOLD}Welcome to the WoW Combat Log Parser Installation Wizard${NC}"
    echo -e "This wizard will guide you through the installation process.\n"

    # Check if already installed
    if [[ -f ".env" ]] && [[ -f "docker-compose.yml" ]]; then
        print_warning "Existing installation detected"
        echo "Do you want to reinstall/reconfigure?"
        prompt_with_default "Continue? (y/n)" "n" "reinstall"

        if [[ "$reinstall" != "y" ]] && [[ "$reinstall" != "Y" ]]; then
            echo "Installation cancelled."
            exit 0
        fi

        # Backup existing configuration
        cp .env .env.backup.$(date +%Y%m%d_%H%M%S)
        print_info "Backed up existing configuration"
    fi

    # Run installation steps
    check_requirements
    configure_installation
    create_directories
    generate_configs
    build_docker_images
    install_cli
    start_services
    create_uninstall_script

    # Show summary
    show_summary

    # Save installation info
    cat > .installation_info << EOF
Installation Date: $(date)
Installation Mode: $INSTALL_MODE
API Port: $API_PORT
Web Port: $NGINX_PORT
Grafana Port: $GRAFANA_PORT
Monitoring Enabled: $ENABLE_MONITORING
SSL Enabled: $ENABLE_SSL
EOF

    exit 0
}

# Handle script arguments
case "${1:-}" in
    --help|-h)
        echo "WoW Combat Log Parser - Installation Wizard"
        echo ""
        echo "Usage: ./install.sh [options]"
        echo ""
        echo "Options:"
        echo "  --help, -h     Show this help message"
        echo "  --uninstall    Run the uninstaller"
        echo "  --version      Show version information"
        echo ""
        echo "Run without arguments for interactive installation."
        exit 0
        ;;
    --uninstall)
        if [[ -f "uninstall.sh" ]]; then
            ./uninstall.sh
        else
            echo "Uninstaller not found. Please run the installer first."
            exit 1
        fi
        exit 0
        ;;
    --version)
        echo "WoW Combat Log Parser Installer v1.0.0"
        exit 0
        ;;
esac

# Run main installation
main "$@"