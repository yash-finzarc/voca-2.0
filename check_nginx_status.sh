#!/bin/bash
# Quick diagnostic script to check nginx status and port 443

echo "=== Nginx Status Check ==="
echo ""

echo "1. Checking nginx service status..."
sudo systemctl status nginx --no-pager -l | head -10
echo ""

echo "2. Checking if nginx is listening on port 443..."
sudo netstat -tlnp 2>/dev/null | grep :443 || sudo ss -tlnp 2>/dev/null | grep :443
echo ""

echo "3. Checking nginx configuration..."
sudo nginx -t
echo ""

echo "4. Checking if config file is enabled..."
ls -la /etc/nginx/sites-enabled/ | grep voca || echo "⚠️  voca config not found in sites-enabled"
echo ""

echo "5. Checking FastAPI server on port 8000..."
curl -s http://localhost:8000/health 2>/dev/null || echo "⚠️  FastAPI server not responding on port 8000"
echo ""

echo "=== Recommendations ==="
echo "If nginx is not running: sudo systemctl start nginx"
echo "If port 443 is not listening: Check nginx logs and configuration"
echo "If config is not enabled: sudo ln -s /etc/nginx/sites-available/voca-2.duckdns.org /etc/nginx/sites-enabled/"

