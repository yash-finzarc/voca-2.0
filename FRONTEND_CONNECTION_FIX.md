# Fix: Frontend Cannot Connect to Linode Backend

## 🔴 Problem

Your frontend is showing:
```
Failed to connect to http://172.105.50.83:8000/api/twilio/call-status/summary?limit=15
Network Error: Failed to connect
```

This means:
- ✅ Frontend is correctly configured (using Linode URL)
- ❌ Cannot connect to backend (network/connectivity issue)

## 🎯 Possible Causes

1. **Backend server not running on Linode**
2. **CORS not configured for `http://localhost:3000`**
3. **Firewall blocking port 8000 on Linode**
4. **Backend not listening on `0.0.0.0:8000`**

---

## ✅ Solutions

### Solution 1: Verify Backend is Running on Linode

**On your Linode server, check:**

```bash
# SSH into Linode
ssh your-user@172.105.50.83

# Check if backend is running
ps aux | grep python
# Should show: python main_api_server.py

# Or check if port 8000 is listening
netstat -tlnp | grep 8000
# or
ss -tlnp | grep 8000
# Should show: 0.0.0.0:8000 (not 127.0.0.1:8000)

# If not running, start it:
cd ~/voca-2.0
python main_api_server.py
```

**Test from Linode itself:**
```bash
curl http://localhost:8000/health
# Should return: {"status":"healthy"}
```

### Solution 2: Update CORS Configuration on Linode

**The backend needs to allow your frontend origin.**

**On Linode, edit `.env` file:**

```bash
cd ~/voca-2.0
nano .env
```

**Add or update `CORS_ORIGINS`:**

```env
CORS_ORIGINS=http://localhost:3000,http://localhost:3001,https://your-frontend.vercel.app
```

**Important:**
- Include `http://localhost:3000` for local development
- Include your production frontend URL (Vercel, custom domain, etc.)
- Comma-separated, no spaces (spaces will be trimmed)

**Example:**
```env
CORS_ORIGINS=http://localhost:3000,http://localhost:3001,https://voca-frontend.vercel.app
```

**Restart backend after updating `.env`:**

```bash
# Stop current server (Ctrl+C)
python main_api_server.py
```

### Solution 3: Check Linode Firewall

**On Linode, check firewall:**

```bash
# Check UFW status (Ubuntu/Debian)
sudo ufw status

# Check firewalld (CentOS/RHEL)
sudo firewall-cmd --state
sudo firewall-cmd --list-ports

# Allow port 8000 if needed:
# For UFW:
sudo ufw allow 8000/tcp
sudo ufw reload

# For firewalld:
sudo firewall-cmd --permanent --add-port=8000/tcp
sudo firewall-cmd --reload
```

**Also check Linode Cloud Firewall (in Linode Dashboard):**
1. Go to Linode Dashboard
2. Select your Linode
3. Go to "Networking" tab
4. Check "Firewalls" section
5. Ensure port 8000 is allowed for inbound connections

### Solution 4: Verify Backend is Listening on 0.0.0.0

**Check `main_api_server.py` on Linode:**

The backend should listen on `0.0.0.0:8000`, not `127.0.0.1:8000`:

```python
uvicorn.run(
    "src.voca.api:app",
    host="0.0.0.0",  # ← Must be 0.0.0.0 (not 127.0.0.1)
    port=8000,
    log_level="info",
    reload=True
)
```

---

## 🧪 Testing Steps

### Test 1: Backend Health from Your Local Computer

**From your local computer:**

```bash
curl http://172.105.50.83:8000/health
```

**Expected:**
- ✅ `{"status":"healthy"}` - Backend is accessible
- ❌ `Connection refused` - Backend not running or firewall blocking
- ❌ `Connection timed out` - Firewall or network issue
- ❌ `Failed to connect` - Server not accessible

### Test 2: CORS Configuration

**From your local computer (simulate frontend request):**

```bash
curl -H "Origin: http://localhost:3000" \
     -H "Access-Control-Request-Method: GET" \
     -X OPTIONS \
     http://172.105.50.83:8000/api/twilio/call-status/summary \
     -v
```

**Check for:**
- `Access-Control-Allow-Origin: http://localhost:3000` in response headers
- Status `200 OK` (not 403 or CORS error)

### Test 3: Direct API Call

**From your local computer:**

```bash
curl http://172.105.50.83:8000/api/twilio/configured
```

**Expected:**
- ✅ `{"configured": true}` or `{"configured": false}` - Server accessible
- ❌ `Connection refused` - Server not running

### Test 4: Browser Console

**Open your frontend in browser:**
1. Open DevTools (F12) → Network tab
2. Try making an API request
3. Check the error:
   - **CORS error** → Backend CORS not configured correctly
   - **Connection refused** → Backend not running or firewall
   - **Timeout** → Network/firewall issue

---

## 📋 Quick Checklist

**On Linode Server:**
- [ ] Backend server is running (`python main_api_server.py`)
- [ ] Server is listening on `0.0.0.0:8000` (not `127.0.0.1:8000`)
- [ ] `.env` has `CORS_ORIGINS` with `http://localhost:3000`
- [ ] Firewall allows port 8000 (`sudo ufw allow 8000/tcp`)
- [ ] Linode Cloud Firewall allows port 8000
- [ ] Test `curl http://localhost:8000/health` works on Linode

**From Your Local Computer:**
- [ ] `curl http://172.105.50.83:8000/health` returns `{"status":"healthy"}`
- [ ] Frontend `.env.local` has `NEXT_PUBLIC_API_BASE_URL=http://172.105.50.83:8000`
- [ ] Frontend dev server restarted after setting `.env.local`

---

## 🔧 Step-by-Step Fix

### Step 1: Verify Backend is Running on Linode

```bash
# SSH into Linode
ssh your-user@172.105.50.83

# Check if running
ps aux | grep "main_api_server.py"

# If not running:
cd ~/voca-2.0
python main_api_server.py
```

### Step 2: Update CORS on Linode

```bash
# On Linode:
cd ~/voca-2.0
nano .env
```

Add or update:
```env
CORS_ORIGINS=http://localhost:3000,http://localhost:3001,https://your-frontend.vercel.app
```

Save (Ctrl+X, Y, Enter)

### Step 3: Allow Firewall Port 8000

```bash
# On Linode:
sudo ufw allow 8000/tcp
sudo ufw reload

# Verify:
sudo ufw status
```

### Step 4: Restart Backend

```bash
# On Linode:
# Stop current server (Ctrl+C)
cd ~/voca-2.0
python main_api_server.py
```

### Step 5: Test from Local Computer

```bash
# From your local computer:
curl http://172.105.50.83:8000/health
```

Should return: `{"status":"healthy"}`

---

## 🐛 Troubleshooting

### Still Getting "Connection Refused"?

1. **Check if backend is actually running:**
   ```bash
   # On Linode:
   ps aux | grep python
   ```

2. **Check if port 8000 is listening:**
   ```bash
   # On Linode:
   netstat -tlnp | grep 8000
   # Should show: 0.0.0.0:8000
   ```

3. **Check firewall:**
   ```bash
   # On Linode:
   sudo ufw status
   sudo iptables -L -n | grep 8000
   ```

4. **Check Linode Cloud Firewall** in Linode Dashboard

### Still Getting CORS Error?

1. **Verify CORS_ORIGINS in .env:**
   ```bash
   # On Linode:
   cat .env | grep CORS_ORIGINS
   ```

2. **Check backend logs** - should show:
   ```
   CORS allowed origins: ['http://localhost:3000', ...]
   ```

3. **Restart backend** after changing CORS_ORIGINS

4. **Verify exact frontend URL** matches what's in CORS_ORIGINS

---

## 💡 Most Common Issue

**The most common issue is CORS not configured for `http://localhost:3000`.**

**Fix:**
1. Add `CORS_ORIGINS=http://localhost:3000` to `.env` on Linode
2. Restart backend server

---

## ✅ Success Indicators

After fixing, you should see:

1. ✅ `curl http://172.105.50.83:8000/health` returns `{"status":"healthy"}`
2. ✅ Frontend can make API requests without CORS errors
3. ✅ Network tab shows `200 OK` responses
4. ✅ No "Connection refused" errors

