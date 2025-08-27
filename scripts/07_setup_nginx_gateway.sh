#!/usr/bin/env bash
set -euo pipefail

# Setup NGINX WebSocket gateway for automatic round-robin across sherpa workers
# This exposes a single port 8000 that automatically distributes to 8001, 8002, 8003

echo "=== Setting up NGINX WebSocket Gateway ==="

# Install NGINX
echo "Installing NGINX..."
apt-get update && apt-get install -y nginx

# Backup default config if it exists
if [ -f /etc/nginx/sites-enabled/default ]; then
    echo "Backing up default NGINX config..."
    mv /etc/nginx/sites-enabled/default /etc/nginx/sites-enabled/default.bak || true
fi

# Create sherpa WebSocket gateway configuration
echo "Creating NGINX configuration for WebSocket gateway..."
cat > /etc/nginx/sites-available/sherpa-ws.conf << 'NGINX_CONF'
upstream sherpa_upstream {
    least_conn;
    server 127.0.0.1:8001 max_fails=3 fail_timeout=5s;
    server 127.0.0.1:8002 max_fails=3 fail_timeout=5s;
    server 127.0.0.1:8003 max_fails=3 fail_timeout=5s;
}

server {
    listen 8000;                       # public port
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
NGINX_CONF

# Enable the configuration
ln -sf /etc/nginx/sites-available/sherpa-ws.conf /etc/nginx/sites-enabled/sherpa-ws.conf

# Test NGINX configuration
echo "Testing NGINX configuration..."
if nginx -t; then
    echo "✓ NGINX configuration is valid"
else
    echo "✗ NGINX configuration has errors"
    exit 1
fi

# Start/restart NGINX (detect systemd availability)
echo "Starting NGINX..."
if systemctl is-system-running >/dev/null 2>&1 || [ -d /run/systemd/system ]; then
    # systemd is available
    echo "Using systemd to manage NGINX..."
    systemctl enable nginx
    systemctl restart nginx
else
    # No systemd, start nginx directly
    echo "systemd not available, starting NGINX directly..."
    # Stop any existing nginx processes
    pkill nginx || true
    sleep 2
    # Start nginx in daemon mode
    nginx -t && nginx
    echo "NGINX started in daemon mode"
fi

# Verify NGINX is running
echo "Verifying NGINX is running..."
sleep 2
if pgrep nginx >/dev/null 2>&1; then
    echo "✓ NGINX is running"
    echo "✓ Listening on port 8000"
else
    echo "✗ NGINX failed to start"
    echo "Troubleshooting:"
    echo "  - Check logs: tail -f /var/log/nginx/error.log"
    echo "  - Test config: nginx -t"
    echo "  - Manual start: nginx"
    exit 1
fi

echo ""
echo "=== NGINX Gateway Configuration Complete ==="
echo "Gateway listening on: port 8000 (public)"
echo "Backend workers: 127.0.0.1:8001, 8002, 8003"
echo "Load balancing: least_conn (least connections)"
echo ""
echo "Usage:"
echo "1. Workers already started on ports 8001-8003"
echo "2. Connect clients to: ws://your-server:8000"
echo "3. NGINX will automatically distribute connections across workers"
echo ""
echo "Management:"
if systemctl is-system-running >/dev/null 2>&1 || [ -d /run/systemd/system ]; then
    echo "  Check status: systemctl status nginx"
    echo "  Stop/start: systemctl stop/start nginx"
else
    echo "  Check status: pgrep nginx"
    echo "  Stop: pkill nginx"  
    echo "  Start: nginx"
fi
echo "  Check logs: tail -f /var/log/nginx/error.log"
