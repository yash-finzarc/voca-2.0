#!/bin/bash
# Comprehensive nginx diagnosis script

echo "==================================================================="
echo "Nginx Diagnosis Script"
echo "==================================================================="
echo ""

echo "1. Checking nginx service status..."
sudo systemctl status nginx --no-pager -l
echo ""

echo "2. Testing nginx configuration (this will show the actual error)..."
echo "---"
sudo nginx -t
NGINX_TEST_EXIT=$?
echo "---"
echo ""

if [ $NGINX_TEST_EXIT -ne 0 ]; then
    echo "⚠️  Nginx configuration test FAILED (exit code: $NGINX_TEST_EXIT)"
    echo ""
fi

echo "3. Checking nginx error log (last 20 lines)..."
echo "---"
sudo tail -20 /var/log/nginx/error.log 2>/dev/null || echo "No error log found or cannot access"
echo "---"
echo ""

echo "4. Checking if SSL certificate files exist..."
CERT_PATH="/etc/letsencrypt/live/voca-2.duckdns.org"
if [ -d "$CERT_PATH" ]; then
    echo "✓ Certificate directory exists: $CERT_PATH"
    ls -la "$CERT_PATH" 2>/dev/null | grep -E "(fullchain|privkey)" || echo "⚠️  Certificate files not found"
else
    echo "✗ Certificate directory does NOT exist: $CERT_PATH"
fi
echo ""

echo "5. Checking nginx config file location..."
if [ -f "/etc/nginx/sites-available/voca-2.duckdns.org" ]; then
    echo "✓ Config file exists: /etc/nginx/sites-available/voca-2.duckdns.org"
else
    echo "✗ Config file does NOT exist: /etc/nginx/sites-available/voca-2.duckdns.org"
fi

if [ -L "/etc/nginx/sites-enabled/voca-2.duckdns.org" ]; then
    echo "✓ Symlink exists: /etc/nginx/sites-enabled/voca-2.duckdns.org"
elif [ -f "/etc/nginx/sites-enabled/voca-2.duckdns.org" ]; then
    echo "⚠️  File exists but is not a symlink: /etc/nginx/sites-enabled/voca-2.duckdns.org"
else
    echo "✗ Symlink does NOT exist: /etc/nginx/sites-enabled/voca-2.duckdns.org"
fi
echo ""

echo "6. Checking if port 443 is in use by another process..."
sudo netstat -tlnp 2>/dev/null | grep :443 || sudo ss -tlnp 2>/dev/null | grep :443 || echo "Port 443 is not in use"
echo ""

echo "==================================================================="
echo "Diagnosis Complete"
echo "==================================================================="
echo ""
echo "Next steps based on the output above:"
echo "1. If nginx -t shows an error, fix that error"
echo "2. If SSL certificates are missing, run the SSL setup script"
echo "3. If config file is missing, copy it from the repo"
echo "4. If symlink is missing, create it: sudo ln -s /etc/nginx/sites-available/voca-2.duckdns.org /etc/nginx/sites-enabled/"
echo "5. After fixing, run: sudo nginx -t && sudo systemctl start nginx"

