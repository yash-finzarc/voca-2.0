# 🔧 FIXED: Frontend Not Connecting to Linode Backend

## ✅ What I Fixed

### 1. Backend CORS Configuration
- ✅ Updated `src/voca/api.py` to support dynamic CORS origins via `CORS_ORIGINS` environment variable
- ✅ Backend can now accept frontend URLs from environment variable
- ✅ Logs CORS configuration for debugging

## 📋 What YOU Need To Do

### Frontend (Local - Your Computer)

**1. Go to your FRONTEND directory:**
```powershell
cd C:\path\to\your\frontend-project
```

**2. Create `.env.local` file in frontend root:**
```env
NEXT_PUBLIC_API_BASE_URL=http://172.105.50.83:8000
```

**3. Restart Next.js server:**
```bash
# Stop current server (Ctrl+C)
npm run dev
```

**✅ Verify:** Console should NOT show "No NEXT_PUBLIC_API_BASE_URL configured"

---

### Backend (Linode Server - Remote)

**1. SSH into Linode:**
```bash
ssh your-user@172.105.50.83
```

**2. Edit `.env` file in VOCA project:**
```env
CORS_ORIGINS=http://localhost:3000,https://your-frontend-url.vercel.app
```
*Replace `your-frontend-url.vercel.app` with your actual frontend URL*

**3. Restart backend:**
```bash
# If using systemd:
sudo systemctl restart voca-backend

# Or if running manually:
python main_api_server.py
```

---

## 🎯 Quick Checklist

### Frontend (Your Computer):
- [ ] `.env.local` file created in frontend root
- [ ] Contains: `NEXT_PUBLIC_API_BASE_URL=http://172.105.50.83:8000`
- [ ] Next.js server restarted after creating file
- [ ] Console shows Linode URL (not localhost:8000)

### Backend (Linode Server):
- [ ] `.env` file updated with `CORS_ORIGINS`
- [ ] CORS_ORIGINS includes your frontend URL
- [ ] Backend server restarted
- [ ] Firewall allows port 8000

---

## 🧪 Test Connection

**From your local computer:**
```bash
curl http://172.105.50.83:8000/health
```

Should return: `{"status":"healthy"}`

**From browser:**
- Open your frontend app
- Open DevTools (F12) → Network tab
- Try making an API request
- Check for CORS errors

---

## 📚 Documentation Created

1. **`LINODE_DEPLOYMENT_GUIDE.md`** - Complete deployment guide
2. **`FRONTEND_ENV_SETUP.md`** - Detailed frontend setup instructions
3. **`QUICK_FIX_STEPS.txt`** - Quick reference

---

## 🐛 Still Having Issues?

### Common Problems:

1. **Frontend still shows "No NEXT_PUBLIC_API_BASE_URL configured"**
   - ❌ You didn't create `.env.local`
   - ❌ Wrong file location (must be in frontend root)
   - ❌ Wrong variable name
   - ❌ Server not restarted

2. **CORS errors in browser**
   - ❌ Frontend URL not in backend `CORS_ORIGINS`
   - ❌ Backend not restarted after changing `.env`
   - ❌ URL mismatch (http vs https)

3. **Connection refused**
   - ❌ Backend not running on Linode
   - ❌ Firewall blocking port 8000
   - ❌ Wrong IP address

---

## 💡 Next Steps

1. ✅ Complete frontend `.env.local` setup
2. ✅ Complete backend `CORS_ORIGINS` setup on Linode
3. ✅ Test connection
4. ✅ Deploy frontend to Vercel (if applicable)
5. ✅ Add environment variable in Vercel dashboard too

---

## 🆘 Need Help?

Check these files for detailed instructions:
- `FRONTEND_ENV_SETUP.md` - Frontend setup
- `LINODE_DEPLOYMENT_GUIDE.md` - Backend setup
- `QUICK_FIX_STEPS.txt` - Quick reference

