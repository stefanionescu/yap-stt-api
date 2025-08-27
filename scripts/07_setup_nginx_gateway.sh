#!/usr/bin/env bash
set -euo pipefail

# Setup NGINX WebSocket gateway for automatic round-robin across sherpa workers
# This exposes a single port 8000 that automatically distributes to 8001, 8002, 8003

echo "=== Setting up NGINX WebSocket Gateway ==="

# Install NGINX
echo "Installing NGINX..."
apt-get update && apt-get install -y nginx

# Stop any existing nginx processes
pkill nginx || true
sleep 2

# Create a complete, self-contained nginx.conf (no sites-enabled complexity)
echo "Creating complete NGINX configuration..."
cat > /etc/nginx/nginx.conf << 'NGINX_CONF'
user www-data;
worker_processes auto;
pid /run/nginx.pid;

events {
    worker_connections 768;
}

http {
    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    keepalive_timeout 65;
    
    include /etc/nginx/mime.types;
    default_type application/octet-stream;
    
    access_log /var/log/nginx/access.log;
    error_log /var/log/nginx/error.log;
    
    # Sherpa WebSocket Gateway Configuration
    upstream sherpa_upstream {
        least_conn;
        server 127.0.0.1:8001 max_fails=3 fail_timeout=5s;
        server 127.0.0.1:8002 max_fails=3 fail_timeout=5s;
        server 127.0.0.1:8003 max_fails=3 fail_timeout=5s;
    }

    server {
        listen 8000;
        
        location / {
            proxy_pass http://sherpa_upstream;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            
            # WebSocket and streaming optimizations
            proxy_read_timeout 3600s;
            proxy_send_timeout 3600s;
            proxy_connect_timeout 10s;
            proxy_buffering off;
            proxy_cache off;
        }
    }
}
NGINX_CONF

# Test NGINX configuration
echo "Testing NGINX configuration..."
if nginx -t; then
    echo "✓ NGINX configuration is valid"
else
    echo "✗ NGINX configuration has errors"
    nginx -t
    exit 1
fi

# Start NGINX
echo "Starting NGINX..."
nginx

# Verify NGINX is running and listening on port 8000
echo "Verifying NGINX is running..."
sleep 2
if pgrep nginx >/dev/null 2>&1 && ss -tulpn | grep -q ":8000 "; then
    echo "✓ NGINX is running and listening on port 8000"
else
    echo "✗ NGINX failed to start properly"
    echo "Debug info:"
    echo "  NGINX processes: $(pgrep nginx || echo 'none')"
    echo "  Port 8000 status: $(ss -tulpn | grep :8000 || echo 'not listening')"
    echo "  Error log:"
    tail -10 /var/log/nginx/error.log 2>/dev/null || echo "No error log"
    exit 1
fi

echo ""
echo "=== NGINX Gateway Configuration Complete ==="
echo "Gateway listening on: port 8000 (public)"
echo "Backend workers: 127.0.0.1:8001, 8002, 8003"
echo "Load balancing: least_conn (least connections)"
echo ""
echo "Usage:"
echo "1. Workers should be running on ports 8001-8003"
echo "2. Connect clients to: ws://your-server:8000"
echo "3. NGINX will automatically distribute connections across workers"
echo ""
echo "Management:"
echo "  Check status: pgrep nginx"
echo "  Stop: pkill nginx"
echo "  Start: nginx"
echo "  Check logs: tail -f /var/log/nginx/error.log"