# How to Start the VOCA Backend Server

## Quick Start

The backend API server must be running for the frontend to work. Here's how to start it:

### Option 1: Simple Start (Recommended)
```bash
python main_api_server.py
```

The server will start on **http://localhost:8000**

### Option 2: Using Uvicorn Directly
```bash
uvicorn src.voca.api:app --host 0.0.0.0 --port 8000 --reload
```

## Verify Server is Running

1. **Check the console output** - You should see:
   ```
   Starting VOCA API Server...
   API will be available at http://localhost:8000
   ```

2. **Test the connection**:
   ```bash
   python test_backend_connection.py
   ```

3. **Open in browser**:
   - API Docs: http://localhost:8000/docs
   - Health Check: http://localhost:8000/health
   - Root: http://localhost:8000/

## Frontend Configuration

If your frontend is trying to connect but getting "Failed to fetch" errors:

1. **Make sure the backend is running** (see above)

2. **Check your frontend's API URL configuration**:
   - For local development: `http://localhost:8000`
   - For ngrok tunnel: Use the ngrok URL from `/api/ngrok/status`

3. **Verify CORS settings**:
   - The backend allows: `localhost:3000`, `localhost:3001`, and Vercel production URL
   - If using a different port, you may need to update CORS in `src/voca/api.py`

## Troubleshooting

### Port 8000 Already in Use
```bash
# Windows - Find what's using port 8000
netstat -ano | findstr :8000

# Kill the process (replace PID with actual process ID)
taskkill /PID <PID> /F
```

### Server Won't Start
1. Check for syntax errors (should be fixed now)
2. Verify all dependencies are installed: `pip install -r requirements.txt`
3. Check Python version: `python --version` (should be 3.10+)

### Frontend Still Can't Connect
1. Make sure backend is running: `python test_backend_connection.py`
2. Check browser console for CORS errors
3. Verify the API URL in your frontend's `.env.local` or config file
4. Try accessing the API directly in browser: http://localhost:8000/health

## What Was Fixed

- ✅ Fixed syntax error in `src/voca/system_prompt.py` (global declaration issues)
- ✅ Created diagnostic tool: `test_backend_connection.py`

## Next Steps

Once the backend is running:
1. The frontend should be able to connect
2. Ngrok tunnel will start automatically (if pyngrok is installed)
3. You can start the Twilio server via the API: `POST /api/twilio/start-server`

