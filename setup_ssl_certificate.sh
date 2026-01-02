#!/bin/bash
#
# SSL Certificate Setup Script for voca-2.duckdns.org
# Run this script on your server to set up SSL certificate and configure nginx
#
# Prerequisites:
# 1. voca-2.duckdns.org is configured in DuckDNS pointing to your server IP
# 2. Port 80 and 443 are open in firewall
# 3. Certbot is installed (sudo apt-get install certbot)
#

set -e  # Exit on error

echo "=========================================="
echo "SSL Certificate Setup for voca-2.duckdns.org"
echo "=========================================="
echo ""

# Step 1: Verify prerequisites
echo "Step 1: Verifying prerequisites..."
echo ""

# Check DNS resolution
echo "Checking DNS resolution..."
if nslookup voca-2.duckdns.org > /dev/null 2>&1; then
    echo "✓ DNS resolution successful"
    IP=$(nslookup voca-2.duckdns.org | grep -A 1 "Name:" | tail -1 | awk '{print $2}')
    echo "  Domain resolves to: $IP"
else
    echo "✗ DNS resolution failed!"
    echo "  Please configure voca-2.duckdns.org in DuckDNS first"
    exit 1
fi

# Check if certbot is installed
if ! command -v certbot &> /dev/null; then
    echo "✗ Certbot is not installed"
    echo "  Install with: sudo apt-get update && sudo apt-get install certbot"
    exit 1
else
    echo "✓ Certbot is installed"
fi

echo ""
echo "Step 2: Stopping nginx (required for standalone mode)..."
sudo systemctl stop nginx || echo "  (nginx was already stopped)"
echo "✓ Nginx stopped"
echo ""

# Step 2: Get SSL certificate
echo "Step 3: Getting SSL certificate..."
echo "  This will use Let's Encrypt to issue a certificate for voca-2.duckdns.org"
echo "  Certbot will temporarily start a web server on port 80"
echo ""
read -p "Press Enter to continue with certificate generation..."
sudo certbot certonly --standalone -d voca-2.duckdns.org

if [ $? -eq 0 ]; then
    echo ""
    echo "✓ Certificate obtained successfully!"
    echo "  Certificate location: /etc/letsencrypt/live/voca-2.duckdns.org/"
else
    echo ""
    echo "✗ Certificate generation failed!"
    echo "  Please check the error messages above"
    exit 1
fi

echo ""
echo "Step 4: Verifying certificate files exist..."
if [ -f "/etc/letsencrypt/live/voca-2.duckdns.org/fullchain.pem" ] && \
   [ -f "/etc/letsencrypt/live/voca-2.duckdns.org/privkey.pem" ]; then
    echo "✓ Certificate files found"
else
    echo "✗ Certificate files not found!"
    exit 1
fi

echo ""
echo "=========================================="
echo "Certificate setup complete!"
echo "=========================================="
echo ""
echo "Next steps (manual):"
echo "1. Copy nginx_voca2_duckdns_org.conf to /etc/nginx/sites-available/voca-2.duckdns.org"
echo "2. Create symlink: sudo ln -s /etc/nginx/sites-available/voca-2.duckdns.org /etc/nginx/sites-enabled/voca-2.duckdns.org"
echo "3. Remove old config: sudo rm -f /etc/nginx/sites-enabled/voca2.duckdns.org"
echo "4. Test nginx: sudo nginx -t"
echo "5. Start nginx: sudo systemctl start nginx"
echo "6. Check status: sudo systemctl status nginx"
echo ""

