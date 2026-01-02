# SSL Certificate Setup Instructions for voca-2.duckdns.org

## Quick Start

1. **Run the setup script on your server:**
   ```bash
   chmod +x setup_ssl_certificate.sh
   ./setup_ssl_certificate.sh
   ```

2. **Or follow the manual steps below:**

## Manual Setup Steps

### Step 1: Verify Prerequisites

```bash
# Check DNS resolution
nslookup voca-2.duckdns.org
# Should show: Address: 172.105.50.83

# Verify certbot is installed
certbot --version
# If not installed: sudo apt-get update && sudo apt-get install certbot
```

### Step 2: Get SSL Certificate

```bash
# Make sure nginx is stopped
sudo systemctl stop nginx

# Get certificate using standalone mode
sudo certbot certonly --standalone -d voca-2.duckdns.org

# Follow the prompts (enter email, agree to terms, etc.)
```

### Step 3: Update Nginx Configuration

**On your server, run:**

```bash
# Remove old config files
sudo rm -f /etc/nginx/sites-enabled/voca2.duckdns.org
sudo rm -f /etc/nginx/sites-available/voca2.duckdns.org

# Create new config file
sudo nano /etc/nginx/sites-available/voca-2.duckdns.org
```

**Copy the entire contents of `nginx_voca2_duckdns_org.conf` into the file, then:**

```bash
# Create symlink to enable the site
sudo ln -s /etc/nginx/sites-available/voca-2.duckdns.org /etc/nginx/sites-enabled/voca-2.duckdns.org

# Remove default site (optional)
sudo rm -f /etc/nginx/sites-enabled/default
```

### Step 4: Test and Start Nginx

```bash
# Test configuration
sudo nginx -t

# If test passes, start nginx
sudo systemctl start nginx

# Check status
sudo systemctl status nginx

# Enable on boot
sudo systemctl enable nginx
```

### Step 5: Verify Everything Works

```bash
# Test from server
curl -k https://localhost/health

# Test from browser
# Visit: https://voca-2.duckdns.org/health
# Should return: {"status":"ok"}
```

## Troubleshooting

### Certbot fails with DNS SERVFAIL
- Make sure `voca-2.duckdns.org` is configured in DuckDNS
- Wait 2-5 minutes for DNS propagation
- Check: `nslookup voca-2.duckdns.org`

### Port 80 already in use
- Make sure nginx is stopped: `sudo systemctl stop nginx`
- Check what's using port 80: `sudo lsof -i :80`

### Nginx fails to start after certificate
- Verify certificate files exist:
  ```bash
  ls -la /etc/letsencrypt/live/voca-2.duckdns.org/
  ```
- Check nginx error logs:
  ```bash
  sudo tail -f /var/log/nginx/error.log
  ```
- Test nginx config:
  ```bash
  sudo nginx -t
  ```

### Certificate renewal
Certbot certificates expire after 90 days. Auto-renewal is usually set up automatically:

```bash
# Test renewal
sudo certbot renew --dry-run

# Check if timer exists
systemctl list-timers | grep certbot
```

## Files Reference

- **Local nginx config:** `nginx_voca2_duckdns_org.conf`
- **Server config location:** `/etc/nginx/sites-available/voca-2.duckdns.org`
- **Certificate location:** `/etc/letsencrypt/live/voca-2.duckdns.org/`

