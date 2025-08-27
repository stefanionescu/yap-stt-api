#!/usr/bin/env bash
set -euo pipefail

# OS/socket limits optimization for high-concurrency WebSocket streaming
# Run this once during system setup or before starting high-load servers

echo "=== Optimizing OS limits for high-concurrency WebSocket streaming ==="

# Raise open files limit for current session
echo "Setting ulimit -n 1048576 for current session..."
ulimit -n 1048576 || true

# Improve socket backlog and network parameters
echo "Configuring network parameters..."

# Increase socket listen backlog
sysctl -w net.core.somaxconn=4096
echo "✓ Set net.core.somaxconn=4096"

# Increase network device backlog queue
sysctl -w net.core.netdev_max_backlog=4096
echo "✓ Set net.core.netdev_max_backlog=4096"

# Expand ephemeral port range for more concurrent connections
sysctl -w net.ipv4.ip_local_port_range="2000 65000"
echo "✓ Set net.ipv4.ip_local_port_range=2000 65000"

# Reduce TIME_WAIT linger time to free sockets faster
sysctl -w net.ipv4.tcp_fin_timeout=15
echo "✓ Set net.ipv4.tcp_fin_timeout=15"

# Optional: Enable TCP window scaling for better throughput
sysctl -w net.ipv4.tcp_window_scaling=1
echo "✓ Set net.ipv4.tcp_window_scaling=1"

# Show current limits
echo ""
echo "=== Current Limits ==="
echo "Open files (ulimit -n): $(ulimit -n)"
echo "somaxconn: $(sysctl -n net.core.somaxconn)"
echo "netdev_max_backlog: $(sysctl -n net.core.netdev_max_backlog)"
echo "ip_local_port_range: $(sysctl -n net.ipv4.ip_local_port_range)"
echo "tcp_fin_timeout: $(sysctl -n net.ipv4.tcp_fin_timeout)"

echo ""
echo "=== Making persistent (optional) ==="
echo "To make these changes persistent across reboots, add to /etc/sysctl.conf:"
echo "net.core.somaxconn=4096"
echo "net.core.netdev_max_backlog=4096"
echo "net.ipv4.ip_local_port_range=2000 65000"
echo "net.ipv4.tcp_fin_timeout=15"
echo "net.ipv4.tcp_window_scaling=1"
echo ""
echo "And add to /etc/security/limits.conf:"
echo "* soft nofile 1048576"
echo "* hard nofile 1048576"

echo ""
echo "✓ OS optimization complete - ready for high-concurrency streaming"
