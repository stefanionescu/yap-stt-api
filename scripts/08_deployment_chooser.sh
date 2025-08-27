#!/usr/bin/env bash
set -euo pipefail

# Interactive deployment chooser - helps pick the right setup
# Use this instead of the full orchestrator if you want more control

echo "=== Sherpa-ONNX Deployment Chooser ==="
echo ""
echo "This script helps you choose the best deployment option for your needs."
echo ""

# Check if system is already set up
if [ -d "/opt/sherpa-onnx" ] && [ -d "/opt/sherpa-models" ]; then
    echo "✓ Sherpa-ONNX appears to be already installed"
    SKIP_SETUP=true
else
    echo "⚠ Sherpa-ONNX not found - will run full setup first"
    SKIP_SETUP=false
fi

echo ""
echo "Choose your deployment strategy:"
echo ""
echo "1. 🎯 Multi-Worker + NGINX Gateway (RECOMMENDED)"
echo "   • Single public port (8000)"
echo "   • Automatic load balancing" 
echo "   • ~100 concurrent streams"
echo "   • Production-ready"
echo ""
echo "2. ⚡ Multi-Worker Direct (NO NGINX)"
echo "   • Multiple public ports (8000-8002)"
echo "   • Client-side load balancing"
echo "   • ~100 concurrent streams"
echo "   • Simpler infrastructure"
echo ""
echo "3. 🔧 Single Worker (SIMPLE)"
echo "   • One public port (8000)"
echo "   • ~30-50 concurrent streams"
echo "   • Testing/development"
echo ""
echo "4. 🗑️ Nuclear Cleanup (Remove Everything)"
echo "   • Complete uninstall"
echo "   • Frees ~7GB+ disk space"
echo ""

read -p "Enter your choice (1-4): " choice

case $choice in
    1)
        echo ""
        echo "🎯 Setting up Multi-Worker + NGINX Gateway..."
        echo ""
        
        if [ "$SKIP_SETUP" = false ]; then
            echo "Step 1: Running full system setup..."
            bash "$(dirname "$0")/00_full_setup_and_run.sh" || exit 1
        fi
        
        echo "Step 2: Starting multi-worker servers (ports 8001-8003)..."
        bash "$(dirname "$0")/04_run_server_multi_int8.sh" &
        
        sleep 5  # Give workers time to start
        
        echo "Step 3: Setting up NGINX gateway (port 8000)..."
        bash "$(dirname "$0")/07_setup_nginx_gateway.sh"
        
        echo ""
        echo "✅ DEPLOYMENT COMPLETE!"
        echo "🌐 Connect clients to: ws://your-server:8000"
        echo "📊 NGINX will automatically round-robin across 3 workers"
        echo ""
        echo "Runpod users: Expose port 8000 only"
        ;;
        
    2)
        echo ""
        echo "⚡ Setting up Multi-Worker Direct (No NGINX)..."
        echo ""
        
        if [ "$SKIP_SETUP" = false ]; then
            echo "Step 1: Running full system setup..."
            bash "$(dirname "$0")/00_full_setup_and_run.sh" || exit 1
        fi
        
        echo "Step 2: Starting multi-worker servers (ports 8000-8002)..."
        WORKERS=3 BASE_PORT=8000 bash "$(dirname "$0")/04_run_server_multi_int8.sh"
        
        echo ""
        echo "✅ DEPLOYMENT COMPLETE!"
        echo "🌐 Connect clients to: ws://your-server:[8000|8001|8002]"
        echo "📊 Round-robin these ports in your client code:"
        echo "   • port = 8000 + (sessionId % 3)"
        echo "   • or random from [8000, 8001, 8002]"
        echo ""
        echo "Runpod users: Expose ports 8000,8001,8002"
        ;;
        
    3)
        echo ""
        echo "🔧 Setting up Single Worker..."
        echo ""
        
        if [ "$SKIP_SETUP" = false ]; then
            echo "Step 1: Running full system setup..."
            bash "$(dirname "$0")/00_full_setup_and_run.sh" || exit 1
        fi
        
        echo "Step 2: Starting single worker server (port 8000)..."
        bash "$(dirname "$0")/03_run_server_single_int8.sh"
        
        echo ""
        echo "✅ DEPLOYMENT COMPLETE!"
        echo "🌐 Connect clients to: ws://your-server:8000"
        echo "📊 ~30-50 concurrent streams supported"
        echo ""
        echo "Runpod users: Expose port 8000"
        ;;
        
    4)
        echo ""
        echo "🗑️ Running Nuclear Cleanup..."
        bash "$(dirname "$0")/99_cleanup_services.sh"
        ;;
        
    *)
        echo "Invalid choice. Please run the script again and choose 1-4."
        exit 1
        ;;
esac
