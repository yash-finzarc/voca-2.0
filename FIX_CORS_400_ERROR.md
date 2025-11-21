# Fix: CORS OPTIONS Requests Returning 400 Bad Request

## 🔴 Problem

Backend logs show:
```
INFO:     124.123.119.85:38091 - "OPTIONS /api/twilio/call-status/summary?limit=15 HTTP/1.1" 400 Bad Request
INFO:     124.123.119.85:38091 - "OPTIONS /health HTTP/1.1" 400 Bad Request
```

This means CORS preflight requests (OPTIONS) are failing.

Also notice:
```
CORS allowed origins: ['https://voca-frontend-self.vercel.app', 'https://localhost:3000']
```

**Issue:** CORS is configured for `https://localhost:3000` but frontend is using `http://localhost:3000` (no 's' in http).

## ✅ Solution

### Step 1: Fix CORS Configuration on Linode

**On your Linode server, edit `.env` file:**

```bash
cd ~/voca-2.0
nano .env
```

**Add or update `CORS_ORIGINS` to use `http://` (not `https://`) for localhost:**

```env
CORS_ORIGINS=http://localhost:3000,http://localhost:3001,https://voca-frontend-self.vercel.app
```

**Important:**
- Use `http://localhost:3000` (not `https://`)
- Comma-separated, no spaces (or spaces will be trimmed)
- Include your production frontend URL if applicable

### Step 2: Restart Backend Server

```bash
# Stop current server (Ctrl+C)
python main_api_server.py
```

### Step 3: Verify CORS is Fixed

**Check backend logs - should show:**
```
CORS allowed origins: ['http://localhost:3000', 'http://localhost:3001', 'https://voca-frontend-self.vercel.app']
```

**Test from frontend:**
- OPTIONS requests should now return 200 OK (not 400)
- Actual GET/POST requests should work

---

## 🐛 What Was Fixed

1. **Custom OPTIONS handler improved** - Now properly checks origin against allowed list
2. **CORS configuration** - You need to update `.env` on Linode to use `http://localhost:3000`

---

## 🧪 Testing

**From your local computer, test CORS:**

```bash
# Test OPTIONS request
curl -X OPTIONS \
  -H "Origin: http://localhost:3000" \
  -H "Access-Control-Request-Method: GET" \
  http://172.105.50.83:8000/api/twilio/call-status/summary \
  -v
```

**Expected:**
- Status: `200 OK`
- Headers should include: `Access-Control-Allow-Origin: http://localhost:3000`

---

## 📋 Quick Checklist

- [ ] Updated `.env` on Linode with `CORS_ORIGINS=http://localhost:3000,...`
- [ ] Restarted backend server
- [ ] CORS logs show `http://localhost:3000` (not `https://`)
- [ ] OPTIONS requests return 200 OK (not 400)
- [ ] Frontend can make API requests

---

## 💡 Common Mistakes

1. **Using `https://localhost:3000`** instead of `http://localhost:3000`
   - Local development uses HTTP, not HTTPS
   - Only production URLs should use HTTPS

2. **Missing origin in CORS_ORIGINS**
   - Make sure your frontend URL is in the list
   - Check for typos (spaces, wrong protocol, wrong port)

3. **Not restarting server**
   - Environment variables are only loaded on server start
   - Must restart after changing `.env`

---

## 🔧 Debugging

**Check what CORS is configured:**

```bash
# On Linode, after restart:
tail -f /path/to/logs | grep "CORS allowed origins"
```

Should show your frontend URL with correct protocol (`http://` or `https://`).

**Check if OPTIONS handler is working:**

```bash
# From local computer:
curl -X OPTIONS \
  -H "Origin: http://localhost:3000" \
  http://172.105.50.83:8000/health \
  -v 2>&1 | grep -E "HTTP|Access-Control"
```

Should show `200 OK` and CORS headers.

