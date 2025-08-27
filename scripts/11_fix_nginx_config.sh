#!/usr/bin/env bash
set -euo pipefail

# Fix NGINX configuration issues - specifically the upstream directive error
# This creates a clean nginx.conf and properly configures sites-enabled

echo "=== Fixing NGINX Configuration ==="

# Stop NGINX if running
pkill nginx || true
sleep 2

# Backup original nginx.conf
cp /etc/nginx/nginx.conf /etc/nginx/nginx.conf.backup

# Create a clean nginx.conf with proper structure
cat > /etc/nginx/nginx.conf << 'NGINX_MAIN_CONF'
user www-data;
worker_processes auto;
pid /run/nginx.pid;
include /etc/nginx/modules-enabled/*.conf;

events {
    worker_connections 768;
    # multi_accept on;
}

http {
    ##
    # Basic Settings
    ##
    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    keepalive_timeout 65;
    types_hash_max_size 2048;

    include /etc/nginx/mime.types;
    default_type application/octet-stream;

    ##
    # SSL Settings
    ##
    ssl_protocols TLSv1 TLSv1.1 TLSv1.2 TLSv1.3; # Dropping SSLv3, ref: POODLE
    ssl_prefer_server_ciphers on;

    ##
    # Logging Settings
    ##
    access_log /var/log/nginx/access.log;
    error_log /var/log/nginx/error.log;

    ##
    # Gzip Settings
    ##
    gzip on;

    ##
    # Virtual Host Configs
    ##
    include /etc/nginx/conf.d/*.conf;
    include /etc/nginx/sites-enabled/*;
}
NGINX_MAIN_CONF

echo "Created clean nginx.conf with proper http block structure"

# Clean up sites-enabled directory
rm -f /etc/nginx/sites-enabled/default*
rm -f /etc/nginx/sites-enabled/sherpa-ws.conf

# Create the sherpa WebSocket configuration
echo "Creating Sherpa WebSocket configuration..."
cat > /etc/nginx/sites-available/sherpa-ws.conf << 'SHERPA_CONF'
upstream sherpa_upstream {
    least_conn;
    server 127.0.0.1:8001 max_fails=3 fail_timeout=5s;
    server 127.0.0.1:8002 max_fails=3 fail_timeout=5s;
    server 127.0.0.1:8003 max_fails=3 fail_timeout=5s;
}

server {
    listen 8000;
    proxy_read_timeout 3600s;
    proxy_send_timeout 3600s;
    proxy_connect_timeout 10s;

    location / {
        proxy_pass http://sherpa_upstream;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Disable buffering for real-time streaming
        proxy_buffering off;
        proxy_cache off;
    }
}
SHERPA_CONF

# Enable the configuration
ln -sf /etc/nginx/sites-available/sherpa-ws.conf /etc/nginx/sites-enabled/sherpa-ws.conf

# Test configuration
echo "Testing NGINX configuration..."
if nginx -t; then
    echo "✅ NGINX configuration is now valid"
    
    # Start NGINX
    echo "Starting NGINX..."
    nginx
    
    # Verify it's running and listening on 8000
    sleep 2
    if ss -tulpn | grep -q ":8000 "; then
        echo "✅ NGINX is listening on port 8000"
    else
        echo "❌ NGINX is not listening on port 8000"
        echo "Check logs: tail -f /var/log/nginx/error.log"
    fi
else
    echo "❌ NGINX configuration still has errors"
    nginx -t
    exit 1
fi

echo ""
echo "=== NGINX Configuration Fixed ==="
echo "Gateway should now be listening on port 8000"
echo "Connect clients to: ws://your-server:8000"
