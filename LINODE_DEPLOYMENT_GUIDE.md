# Linode Backend Deployment Guide

This guide helps you configure your VOCA backend deployed on Linode to work with your frontend.

## 🎯 Overview

Your backend is deployed on Linode at: **172.105.50.83:8000**

For the frontend to connect successfully, you need to:
1. ✅ Configure CORS on the backend to allow your frontend URL
2. ✅ Configure the frontend's `.env` to point to the Linode server
3. ✅ Ensure Linode firewall allows connections on port 8000

---

## 📋 Step 1: Configure Backend CORS

### On your Linode server:

1. **SSH into your Linode server:**
   ```bash
   ssh root@172.105.50.83
   # or
   ssh your-user@172.105.50.83
   ```

2. **Edit the backend's `.env` file** (in the VOCA project directory):
   ```bash
   cd /path/to/voca/project
   nano .env
   # or use vi/vim
   ```

3. **Add your frontend URL(s) to the `CORS_ORIGINS` environment variable:**
   ```env
   # Example for Vercel deployment:
   CORS_ORIGINS=https://your-frontend-app.vercel.app,http://localhost:3000
   
   # Example for custom domain:
   CORS_ORIGINS=https://yourdomain.com,http://localhost:3000
   
   # Example for multiple frontends:
   CORS_ORIGINS=https://app1.vercel.app,https://app2.vercel.app,http://localhost:3000
   ```
   
   **Important:** 
   - Use **comma-separated** URLs (no spaces around commas, or spaces will be trimmed)
   - Include the **full URL** with protocol (`http://` or `https://`)
   - Include `http://localhost:3000` if you want to test locally

4. **Restart your backend server:**
   ```bash
   # If using systemd service:
   sudo systemctl restart voca-backend
   
   # If running manually, stop and restart:
   # Press Ctrl+C to stop, then:
   python main_api_server.py
   
   # If using PM2:
   pm2 restart voca-backend
   ```

5. **Verify CORS is working:**
   ```bash
   # Check the server logs - you should see:
   # "CORS allowed origins: ['https://your-frontend-url.com', ...]"
   ```

---

## 📋 Step 2: Configure Frontend Environment

### In your frontend codebase:

1. **Navigate to your frontend project directory:**
   ```bash
   cd /path/to/your/frontend/project
   ```

2. **Create or edit `.env.local` file** (Next.js uses `.env.local` for local overrides):
   ```bash
   nano .env.local
   # or
   code .env.local
   ```

3. **Add the Linode backend URL:**
   ```env
   NEXT_PUBLIC_API_BASE_URL=http://172.105.50.83:8000
   ```
   
   **Important:**
   - Use `http://` if your Linode server doesn't have SSL
   - Use `https://` if you have SSL configured on Linode
   - The variable name **must** start with `NEXT_PUBLIC_` to be exposed to the browser
   - No trailing slash

4. **For production deployment** (e.g., Vercel), also add it to your deployment platform's environment variables:
   - **Vercel:** Go to Project Settings → Environment Variables
   - Add: `NEXT_PUBLIC_API_BASE_URL` = `http://172.105.50.83:8000`

5. **Restart your Next.js dev server:**
   ```bash
   # Stop the current server (Ctrl+C), then:
   npm run dev
   # or
   yarn dev
   ```

---

## 📋 Step 3: Configure Linode Firewall

### On your Linode server:

1. **Check if firewall is running:**
   ```bash
   sudo ufw status
   # or
   sudo firewall-cmd --state  # for CentOS/RHEL
   ```

2. **Allow port 8000:**
   ```bash
   # For UFW (Ubuntu/Debian):
   sudo ufw allow 8000/tcp
   sudo ufw reload
   
   # For firewalld (CentOS/RHEL):
   sudo firewall-cmd --permanent --add-port=8000/tcp
   sudo firewall-cmd --reload
   
   # For iptables directly:
   sudo iptables -A INPUT -p tcp --dport 8000 -j ACCEPT
   ```

3. **Also check Linode Cloud Firewall** (in Linode dashboard):
   - Go to Linode Dashboard → Your Linode → Networking
   - Check "Firewalls" section
   - Ensure port 8000 is allowed for inbound connections

4. **Verify the port is accessible:**
   ```bash
   # From your local machine, test:
   curl http://172.105.50.83:8000/health
   
   # Should return: {"status":"healthy"}
   ```

---

## 🧪 Testing the Connection

### Test 1: Backend Health Check
```bash
# From your local machine or browser:
curl http://172.105.50.83:8000/health

# Expected response:
# {"status":"healthy"}
```

### Test 2: CORS Configuration
```bash
# Test CORS headers (replace with your frontend URL):
curl -H "Origin: https://your-frontend-app.vercel.app" \
     -H "Access-Control-Request-Method: GET" \
     -X OPTIONS \
     http://172.105.50.83:8000/api/system-prompt/list \
     -v

# Look for: Access-Control-Allow-Origin header in response
```

### Test 3: Frontend Connection
1. Open your frontend app in the browser
2. Open browser DevTools (F12) → Network tab
3. Try making an API request
4. Check for:
   - ✅ Status 200: Success!
   - ❌ CORS error: Frontend URL not in CORS_ORIGINS
   - ❌ Connection refused: Firewall issue or server not running

---

## 🔧 Troubleshooting

### Issue: "CORS policy: No 'Access-Control-Allow-Origin' header"
**Solution:** 
- Check that your frontend URL is in `CORS_ORIGINS` on the backend
- Ensure the URL matches exactly (including `http://` vs `https://`)
- Restart the backend server after changing `.env`

### Issue: "Failed to fetch" / "Connection refused"
**Solution:**
- Check if backend is running: `curl http://172.105.50.83:8000/health`
- Verify firewall allows port 8000
- Check Linode Cloud Firewall settings
- Ensure server is listening on `0.0.0.0:8000` (not `127.0.0.1:8000`)

### Issue: "Network error" in browser console
**Solution:**
- Verify `NEXT_PUBLIC_API_BASE_URL` is set correctly in `.env.local`
- Restart Next.js dev server after changing `.env.local`
- Check browser console for exact error message

### Issue: Frontend can't connect but curl works
**Solution:**
- This is usually a CORS issue
- Double-check `CORS_ORIGINS` includes your frontend URL
- Check browser Network tab → Request Headers → Origin value

---

## 🔐 Security Considerations

### For Production:

1. **Use HTTPS:**
   - Set up SSL/TLS certificate on Linode (Let's Encrypt, Cloudflare, etc.)
   - Update `NEXT_PUBLIC_API_BASE_URL` to use `https://`
   - Update `CORS_ORIGINS` to use `https://` URLs only

2. **Restrict CORS:**
   - Only include production frontend URLs in `CORS_ORIGINS`
   - Remove `localhost` origins for production

3. **Firewall:**
   - Only open port 8000 to specific IPs if possible
   - Or use a reverse proxy (nginx) with SSL termination

---

## 📝 Quick Reference

### Backend `.env` (on Linode):
```env
CORS_ORIGINS=https://your-frontend.vercel.app,http://localhost:3000
```

### Frontend `.env.local`:
```env
NEXT_PUBLIC_API_BASE_URL=http://172.105.50.83:8000
```

### Firewall Command:
```bash
sudo ufw allow 8000/tcp
```

---

## 🎉 Success Checklist

- [ ] Backend `.env` has `CORS_ORIGINS` with frontend URL
- [ ] Backend server restarted after `.env` changes
- [ ] Frontend `.env.local` has `NEXT_PUBLIC_API_BASE_URL` pointing to Linode
- [ ] Frontend dev server restarted after `.env.local` changes
- [ ] Linode firewall allows port 8000
- [ ] `curl http://172.105.50.83:8000/health` returns success
- [ ] Browser can make API requests without CORS errors

---

## 💡 Additional Notes

- **IP Address vs Domain:** Consider setting up a domain name for your Linode server instead of using the IP directly
- **SSL/HTTPS:** For production, use HTTPS. You can use Let's Encrypt for free SSL certificates
- **Reverse Proxy:** Consider using nginx as a reverse proxy for better security and SSL handling

For issues, check:
- Backend logs: `tail -f /path/to/logs/app.log` or server console
- Frontend console: Browser DevTools → Console tab
- Network tab: Browser DevTools → Network tab

