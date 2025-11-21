# Fix: Port 8000 Already in Use on Linode

## 🔴 Problem

When starting the backend server, you see:
```
ERROR:    [Errno 98] Address already in use
```

This means port 8000 is already being used by another process (likely a previous instance of the backend server).

## ✅ Solution

Find and stop the process using port 8000, then restart the server.

---

## 📋 Quick Fix Steps

### Step 1: Find the Process Using Port 8000

**On your Linode server, run:**

```bash
# Find process using port 8000
sudo lsof -i :8000
# or
sudo netstat -tlnp | grep 8000
# or
sudo ss -tlnp | grep 8000
```

This will show something like:
```
COMMAND   PID   USER   FD   TYPE DEVICE SIZE/OFF NODE NAME
python    1234  root   3u  IPv4  12345      0t0  TCP *:8000 (LISTEN)
```

**Note the PID (Process ID)** - in the example above, it's `1234`.

### Step 2: Stop the Process

**Kill the process using its PID:**

```bash
# Replace 1234 with the actual PID from Step 1
sudo kill 1234
```

**Or kill all Python processes (be careful!):**

```bash
# Find all Python processes running main_api_server.py
ps aux | grep main_api_server.py

# Kill them (replace PID with actual process ID)
sudo kill <PID>
```

**Or force kill if regular kill doesn't work:**

```bash
sudo kill -9 <PID>
```

### Step 3: Verify Port is Free

**Check that port 8000 is now free:**

```bash
sudo lsof -i :8000
# Should return nothing (port is free)
```

### Step 4: Start Backend Server Again

**Now start the server:**

```bash
cd ~/voca-2.0
source venv/bin/activate
python main_api_server.py
```

---

## 🔧 Alternative: Kill All Python Processes (Use with Caution)

**If you want to kill all Python processes:**

```bash
# Find all Python processes
ps aux | grep python

# Kill specific ones or all (be careful!)
sudo pkill -f main_api_server.py
# or
sudo pkill -f uvicorn
```

**⚠️ Warning:** This will kill ALL Python processes matching the pattern. Only use if you're sure.

---

## 🧪 Verify It's Working

**After stopping the old process and starting the server:**

1. **Check if server started successfully:**
   ```
   INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
   ```

2. **Test from Linode itself:**
   ```bash
   curl http://localhost:8000/health
   ```
   Should return: `{"status":"healthy"}`

3. **Test from your local computer:**
   ```bash
   curl http://172.105.50.83:8000/health
   ```
   Should return: `{"status":"healthy"}`

---

## 📝 Quick One-Liner Commands

**Find and kill process on port 8000:**

```bash
# Find PID
PID=$(sudo lsof -t -i:8000)

# Kill it
sudo kill $PID

# Or force kill
sudo kill -9 $PID
```

**Or in one command:**

```bash
sudo kill -9 $(sudo lsof -t -i:8000)
```

**⚠️ This will kill any process on port 8000. Make sure that's what you want!**

---

## 🐛 Troubleshooting

### Issue: Process won't die

```bash
# Use force kill
sudo kill -9 <PID>

# Or find and kill all related processes
ps aux | grep python
sudo kill -9 <all_PIDs>
```

### Issue: Permission denied

```bash
# Make sure you're using sudo
sudo kill <PID>

# Or check if you own the process
ps aux | grep python
# Look at the USER column
```

### Issue: Server still won't start

1. **Check if port is really free:**
   ```bash
   sudo lsof -i :8000
   sudo netstat -tlnp | grep 8000
   ```

2. **Check if firewall is blocking:**
   ```bash
   sudo ufw status
   ```

3. **Try a different port temporarily:**
   ```bash
   # Edit main_api_server.py to use port 8001
   # Change: port=8000 to port=8001
   # Then update frontend to use port 8001
   ```

---

## ✅ Success Checklist

- [ ] Found process using port 8000 (`sudo lsof -i :8000`)
- [ ] Killed the process (`sudo kill <PID>`)
- [ ] Verified port is free (`sudo lsof -i :8000` returns nothing)
- [ ] Started backend server (`python main_api_server.py`)
- [ ] Server started without "Address already in use" error
- [ ] Tested with `curl http://localhost:8000/health`

---

## 💡 Prevention: Use Process Manager

To prevent this issue in the future, consider using a process manager like `systemd` or `supervisord`:

### Option 1: systemd Service

Create `/etc/systemd/system/voca-backend.service`:

```ini
[Unit]
Description=VOCA Backend API Server
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/voca-2.0
Environment="PATH=/root/voca-2.0/venv/bin"
ExecStart=/root/voca-2.0/venv/bin/python /root/voca-2.0/main_api_server.py
Restart=always

[Install]
WantedBy=multi-user.target
```

Then:
```bash
sudo systemctl enable voca-backend
sudo systemctl start voca-backend
sudo systemctl status voca-backend
```

This ensures only one instance runs and auto-restarts if it crashes.

---

## 🎯 Summary

**Quick fix:**
```bash
# 1. Find process
sudo lsof -i :8000

# 2. Kill it (replace PID)
sudo kill <PID>

# 3. Start server
python main_api_server.py
```

