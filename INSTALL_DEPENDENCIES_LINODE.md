# Install Dependencies on Linode Server

## 🔴 Problem

Backend server fails to start with:
```
ModuleNotFoundError: No module named 'uvicorn'
```

This means Python dependencies are not installed on your Linode server.

## ✅ Solution

Install all required dependencies using `pip`.

---

## 📋 Steps

### Step 1: SSH into Linode

```bash
ssh your-user@172.105.50.83
```

### Step 2: Navigate to Project Directory

```bash
cd ~/voca-2.0
```

### Step 3: Activate Virtual Environment (if using one)

If you see `(venv)` in your prompt, you're already in a virtual environment. Otherwise:

```bash
# Create virtual environment (if not exists)
python3 -m venv venv

# Activate it
source venv/bin/activate
```

You should see `(venv)` in your prompt.

### Step 4: Install Dependencies

```bash
pip install -r requirements.txt
```

This will install all required packages including:
- `uvicorn` (ASGI server)
- `fastapi` (web framework)
- `twilio` (Twilio SDK)
- And all other dependencies

**This may take a few minutes** depending on your server's internet speed.

### Step 5: Verify Installation

```bash
pip list | grep uvicorn
```

Should show: `uvicorn` with a version number

### Step 6: Start Backend Server

```bash
python main_api_server.py
```

Should now start successfully!

---

## 🔧 Alternative: Install Only Missing Packages

If you want to install just the missing packages:

```bash
pip install uvicorn fastapi
```

But it's better to install all dependencies:

```bash
pip install -r requirements.txt
```

---

## 🐛 Troubleshooting

### Issue: pip not found

```bash
# Try:
python3 -m pip install -r requirements.txt

# Or install pip first:
sudo apt-get update
sudo apt-get install python3-pip  # Ubuntu/Debian
# or
sudo yum install python3-pip      # CentOS/RHEL
```

### Issue: Permission denied

If you get permission errors:

```bash
# Make sure you're in the virtual environment:
source venv/bin/activate

# Or use --user flag:
pip install --user -r requirements.txt
```

### Issue: SSL/TLS errors during installation

```bash
# Try upgrading pip first:
pip install --upgrade pip

# Then install:
pip install -r requirements.txt
```

### Issue: Virtual environment not activating

```bash
# Make sure you're using the right Python version:
python3 --version  # Should be 3.8+

# Create fresh virtual environment:
python3 -m venv venv
source venv/bin/activate

# Then install:
pip install -r requirements.txt
```

---

## 📋 Complete Setup Script

Here's a complete setup script you can run on Linode:

```bash
#!/bin/bash
# Run this script on Linode to set up the backend

cd ~/voca-2.0

# Create virtual environment if not exists
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install dependencies
pip install -r requirements.txt

# Verify installation
pip list | grep uvicorn

echo "Setup complete! You can now run: python main_api_server.py"
```

To use:
1. Save as `setup.sh` on Linode
2. Make executable: `chmod +x setup.sh`
3. Run: `./setup.sh`

---

## ✅ Success Checklist

After installation:
- [ ] `pip list | grep uvicorn` shows uvicorn is installed
- [ ] `pip list | grep fastapi` shows fastapi is installed
- [ ] `python main_api_server.py` starts without errors
- [ ] Backend logs show: "Starting VOCA API Server..."
- [ ] `curl http://localhost:8000/health` works on Linode

---

## 💡 After Installation

Once dependencies are installed:

1. **Make sure .env file has required variables:**
   ```bash
   cat .env | grep -E "TWILIO|CORS"
   ```

2. **Start the backend:**
   ```bash
   python main_api_server.py
   ```

3. **Test from your local computer:**
   ```bash
   curl http://172.105.50.83:8000/health
   ```

---

## 🔗 Next Steps

After installing dependencies:
1. ✅ Install dependencies (this guide)
2. ✅ Add Twilio credentials to `.env` (see `ADD_TWILIO_ENV_LINODE.md`)
3. ✅ Configure CORS in `.env` (see `FRONTEND_CONNECTION_FIX.md`)
4. ✅ Start backend server
5. ✅ Test connection from frontend

