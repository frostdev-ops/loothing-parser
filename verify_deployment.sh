#!/bin/bash

# Deployment Verification Script
# This script checks that all deployment components are ready

set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

echo "======================================"
echo "WoW Combat Log Parser - Deployment Verification"
echo "======================================"
echo

# Check for required files
echo "Checking deployment files..."
required_files=(
    "install.sh"
    "Dockerfile"
    "docker-compose.yml"
    "docker-compose.prod.yml"
    ".env.example"
    ".env.production"
    "DEPLOYMENT.md"
    "requirements.txt"
    "pyproject.toml"
)

all_good=true
for file in "${required_files[@]}"; do
    if [[ -f "$file" ]]; then
        echo -e "${GREEN}✓${NC} $file exists"
    else
        echo -e "${RED}✗${NC} $file is missing"
        all_good=false
    fi
done

echo
echo "Checking directories..."
required_dirs=(
    "src"
    "src/api"
    "src/parser"
    "src/segmentation"
    "src/database"
    "examples"
    "tests"
)

for dir in "${required_dirs[@]}"; do
    if [[ -d "$dir" ]]; then
        echo -e "${GREEN}✓${NC} $dir exists"
    else
        echo -e "${RED}✗${NC} $dir is missing"
        all_good=false
    fi
done

echo
echo "Checking Python modules..."
python3 -c "
import src.parser.events
import src.segmentation.unified_segmenter
import src.database.query
print('✓ Core modules import successfully')
" 2>/dev/null || {
    echo -e "${RED}✗${NC} Python modules import failed"
    all_good=false
}

echo
if [[ "$all_good" == true ]]; then
    echo -e "${GREEN}======================================"
    echo -e "All checks passed! Ready for deployment."
    echo -e "======================================${NC}"
    echo
    echo "To deploy, run: ./install.sh"
else
    echo -e "${RED}======================================"
    echo -e "Some checks failed. Please fix issues before deploying."
    echo -e "======================================${NC}"
    exit 1
fi