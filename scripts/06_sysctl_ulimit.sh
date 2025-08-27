#!/usr/bin/env bash
set -euo pipefail

# OS/socket limits optimization for high-concurrency WebSocket streaming
# Run this once during system setup or before starting high-load servers
# Optimized for Linux/Ubuntu (Runpod)

echo "=== Optimizing OS limits for high-concurrency WebSocket streaming ==="

# Detect OS - these optimizations are for Linux only (Runpod/Ubuntu)
if [[ "$OSTYPE" != "linux-gnu"* ]]; then
    echo "⚠ Skipping network optimizations - Linux/Ubuntu required (current: $OSTYPE)"
    echo "  These settings are for Runpod deployment only"
    echo "✓ ulimit settings still applied for current session"
    echo ""
    ulimit -n 1048576 2>/dev/null || echo "⚠ Could not set ulimit (may need root)"
    exit 0
fi

# Raise open files limit for current session
echo "Setting ulimit -n 1048576 for current session..."
ulimit -n 1048576 || true

# Improve socket backlog and network parameters (container-safe)
echo "Configuring network parameters..."

OPTIMIZATIONS_APPLIED=0

# Increase socket listen backlog
if sysctl -w net.core.somaxconn=4096 2>/dev/null; then
    echo "✓ Set net.core.somaxconn=4096"
    ((OPTIMIZATIONS_APPLIED++))
else
    echo "⚠ Skipped net.core.somaxconn (not available in container)"
fi

# Increase network device backlog queue
if sysctl -w net.core.netdev_max_backlog=4096 2>/dev/null; then
    echo "✓ Set net.core.netdev_max_backlog=4096"
    ((OPTIMIZATIONS_APPLIED++))
else
    echo "⚠ Skipped net.core.netdev_max_backlog (not available in container)"
fi

# Expand ephemeral port range for more concurrent connections
if sysctl -w net.ipv4.ip_local_port_range="2000 65000" 2>/dev/null; then
    echo "✓ Set net.ipv4.ip_local_port_range=2000 65000"
    ((OPTIMIZATIONS_APPLIED++))
else
    echo "⚠ Skipped net.ipv4.ip_local_port_range (not available in container)"
fi

# Reduce TIME_WAIT linger time to free sockets faster
if sysctl -w net.ipv4.tcp_fin_timeout=15 2>/dev/null; then
    echo "✓ Set net.ipv4.tcp_fin_timeout=15"
    ((OPTIMIZATIONS_APPLIED++))
else
    echo "⚠ Skipped net.ipv4.tcp_fin_timeout (not available in container)"
fi

# Optional: Enable TCP window scaling for better throughput
if sysctl -w net.ipv4.tcp_window_scaling=1 2>/dev/null; then
    echo "✓ Set net.ipv4.tcp_window_scaling=1"
    ((OPTIMIZATIONS_APPLIED++))
else
    echo "⚠ Skipped net.ipv4.tcp_window_scaling (not available in container)"
fi

if [ $OPTIMIZATIONS_APPLIED -eq 0 ]; then
    echo "⚠ No network optimizations could be applied (containerized environment)"
    echo "  This is normal in some Runpod containers - server will still work fine"
else
    echo "✓ Applied $OPTIMIZATIONS_APPLIED network optimizations"
fi

# Show current limits (only what's available)
echo ""
echo "=== Current Limits ==="
echo "Open files (ulimit -n): $(ulimit -n)"

# Show only available parameters
sysctl -n net.core.somaxconn 2>/dev/null && echo "somaxconn: $(sysctl -n net.core.somaxconn 2>/dev/null)" || echo "somaxconn: not available"
sysctl -n net.core.netdev_max_backlog 2>/dev/null && echo "netdev_max_backlog: $(sysctl -n net.core.netdev_max_backlog 2>/dev/null)" || echo "netdev_max_backlog: not available"
sysctl -n net.ipv4.ip_local_port_range 2>/dev/null && echo "ip_local_port_range: $(sysctl -n net.ipv4.ip_local_port_range 2>/dev/null)" || echo "ip_local_port_range: not available"
sysctl -n net.ipv4.tcp_fin_timeout 2>/dev/null && echo "tcp_fin_timeout: $(sysctl -n net.ipv4.tcp_fin_timeout 2>/dev/null)" || echo "tcp_fin_timeout: not available"

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
if [ $OPTIMIZATIONS_APPLIED -gt 0 ]; then
    echo "✓ OS optimization complete - ready for high-concurrency streaming"
else
    echo "✓ Basic optimization complete - ulimit set for current session"
    echo "  Network optimizations unavailable in this container environment"
    echo "  Server will still handle high concurrency effectively"
fi
