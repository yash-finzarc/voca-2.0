# Frontend Environment Variable Setup - QUICK FIX

## 🔴 The Problem
Your frontend logs show:
```
[API Client] ⚠️ No NEXT_PUBLIC_API_BASE_URL configured, using default: http://localhost:8000
```

This means the environment variable is **NOT** set in your frontend.

---

## ✅ Solution - 3 Steps

### Step 1: Navigate to Your Frontend Directory

Open your terminal/PowerShell and go to your **frontend** project directory:

```bash
# Example paths - replace with YOUR actual frontend path:
cd C:\Users\Yash\Desktop\voca-frontend
# or
cd C:\Users\Yash\Desktop\frontend
# or wherever your Next.js frontend code is located
```

---

### Step 2: Create/Edit `.env.local` File

**In your FRONTEND directory**, create or edit `.env.local`:

**Windows (PowerShell):**
```powershell
# Navigate to frontend directory first, then:
New-Item -Path .env.local -ItemType File -Force
notepad .env.local
```

**Or manually:**
1. Open your frontend project in File Explorer
2. In the root of the frontend project (same level as `package.json`)
3. Create a new file named `.env.local` (note the dot at the beginning)
4. Open it in Notepad or any text editor

**Add this line to `.env.local`:**
```env
NEXT_PUBLIC_API_BASE_URL=http://172.105.50.83:8000
```

**Important:**
- ✅ Variable name **must** start with `NEXT_PUBLIC_`
- ✅ No spaces around the `=`
- ✅ No quotes needed (unless your URL has special characters)
- ✅ Use `http://` (not `https://` unless your Linode has SSL)

**Save the file!**

---

### Step 3: Restart Next.js Dev Server

**You MUST restart the Next.js server** for environment variables to load:

1. **Stop the current server:**
   - Go to the terminal where `npm run dev` is running
   - Press `Ctrl+C` to stop it

2. **Start it again:**
   ```bash
   npm run dev
   # or
   yarn dev
   ```

3. **Verify it worked:**
   - Check the console output
   - You should **NOT** see the warning anymore
   - You should see: `[API Client] Initialized with base URL: http://172.105.50.83:8000`

---

## 🔍 Verify It's Working

After restarting, check:

1. **Console output** - should show the Linode URL, not `localhost:8000`
2. **Browser console** - open DevTools (F12) → Console tab
3. **Network tab** - make an API request, check the URL

---

## 🐛 Still Not Working?

### Check 1: File Location
Make sure `.env.local` is in the **root** of your frontend project:
```
your-frontend-project/
├── .env.local          ← HERE (same level as package.json)
├── package.json
├── next.config.js
├── app/
└── ...
```

### Check 2: File Name
- ✅ Correct: `.env.local`
- ❌ Wrong: `.env` (use `.env.local` for Next.js)
- ❌ Wrong: `env.local` (missing the dot)

### Check 3: Variable Name
- ✅ Correct: `NEXT_PUBLIC_API_BASE_URL`
- ❌ Wrong: `API_BASE_URL` (missing `NEXT_PUBLIC_` prefix)
- ❌ Wrong: `NEXT_PUBLIC_API_URL` (wrong variable name)

### Check 4: Server Restart
- ✅ Did you restart the server after creating/editing `.env.local`?
- ❌ Next.js only reads `.env.local` on **server start**

### Check 5: Typo Check
Make sure there are no typos:
```env
NEXT_PUBLIC_API_BASE_URL=http://172.105.50.83:8000
#                   ^^^^ Make sure BASE is included
```

---

## 📝 Complete Example

**Your frontend `.env.local` should look like this:**

```env
NEXT_PUBLIC_API_BASE_URL=http://172.105.50.83:8000
```

**That's it! One line only.**

---

## 🧪 Quick Test

After restarting your Next.js server, open your browser console and check:

```javascript
console.log(process.env.NEXT_PUBLIC_API_BASE_URL)
```

Should show: `http://172.105.50.83:8000`

If it shows `undefined`, the environment variable is not set correctly.

---

## 💡 Still Having Issues?

1. **Delete `.env.local`** and create it fresh
2. **Make sure there are no hidden characters** (copy-paste the exact line)
3. **Check your `next.config.js`** - shouldn't override this
4. **Try `.env` instead of `.env.local`** (though `.env.local` is preferred)

---

## 🎯 For Vercel/Production Deployment

When deploying to Vercel, also add the environment variable in Vercel dashboard:

1. Go to your Vercel project
2. Settings → Environment Variables
3. Add: `NEXT_PUBLIC_API_BASE_URL` = `http://172.105.50.83:8000`
4. Redeploy

---

## ✅ Success Checklist

- [ ] `.env.local` file created in frontend root directory
- [ ] File contains: `NEXT_PUBLIC_API_BASE_URL=http://172.105.50.83:8000`
- [ ] File is saved
- [ ] Next.js dev server restarted (`Ctrl+C` then `npm run dev`)
- [ ] Console no longer shows "No NEXT_PUBLIC_API_BASE_URL configured"
- [ ] Console shows: "Initialized with base URL: http://172.105.50.83:8000"

