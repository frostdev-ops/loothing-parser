# Node.js Web Server for WoW Combat Parser Test Suite

FROM node:20-alpine

# Set working directory
WORKDIR /app

# Create non-root user
RUN addgroup -g 1001 -S nodejs && \
    adduser -S nextjs -u 1001

# Install system dependencies
RUN apk add --no-cache \
    curl \
    tini

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm ci --only=production && \
    npm cache clean --force

# Copy application files
COPY . .

# Create necessary directories
RUN mkdir -p uploads logs test-data && \
    chown -R nextjs:nodejs /app

# Set environment
ENV NODE_ENV=production
ENV PORT=3000

# Expose port
EXPOSE 3000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:3000/health || exit 1

# Use tini for proper signal handling
ENTRYPOINT ["/sbin/tini", "--"]

# Switch to non-root user
USER nextjs

# Start the application
CMD ["node", "server.js"]