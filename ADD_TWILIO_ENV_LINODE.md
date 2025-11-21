# Add Twilio Environment Variables to Linode Server

## 🔴 Problem

Your `.env` file on Linode doesn't have Twilio credentials:
```bash
cat .env | grep TWILIO
# Shows nothing - no TWILIO variables
```

This is why `/api/twilio/call-status/summary` returns 400 Bad Request.

## ✅ Solution

Add Twilio credentials to your `.env` file on Linode.

---

## 📋 Step-by-Step Instructions

### Step 1: Check Current .env File

On your Linode server:
```bash
cd ~/voca-2.0
cat .env
```

This will show you what's currently in the file.

### Step 2: Edit .env File

```bash
nano .env
# or
vi .env
```

### Step 3: Add Twilio Credentials

Add these lines to your `.env` file (replace with YOUR actual values):

```env
TWILIO_ACCOUNT_SID=your_twilio_account_sid_here
TWILIO_AUTH_TOKEN=your_twilio_auth_token_here
TWILIO_PHONE_NUMBER=+1XXXXXXXXXX
```

**Important:**
- Replace `your_twilio_account_sid_here` with your actual Twilio Account SID
- Replace `your_twilio_auth_token_here` with your actual Twilio Auth Token
- Replace `+1XXXXXXXXXX` with your actual Twilio phone number (include the + and country code)

**Example:**
```env
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token_here
TWILIO_PHONE_NUMBER=+15551234567
```

**Note:** Replace the placeholder values with your actual Twilio credentials from the Twilio Console.

### Step 4: Save the File

- **nano:** Press `Ctrl+X`, then `Y`, then `Enter`
- **vi:** Press `Esc`, type `:wq`, then `Enter`

### Step 5: Verify the Variables Were Added

```bash
cat .env | grep TWILIO
```

You should now see:
```
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token_here
TWILIO_PHONE_NUMBER=+15551234567
```

(With your actual credentials instead of placeholders)

### Step 6: Restart Backend Server

**Stop the current server:**
- Go to the terminal where `python main_api_server.py` is running
- Press `Ctrl+C` to stop it

**Start it again:**
```bash
cd ~/voca-2.0
python main_api_server.py
```

### Step 7: Test the Endpoint

**From your local computer:**
```bash
curl http://172.105.50.83:8000/api/twilio/configured
```

Should return: `{"configured": true}`

```bash
curl http://172.105.50.83:8000/api/twilio/call-status/summary?limit=15
```

Should return: `{"ongoing": [], "declined": [], "completed": [], "others": []}` (or actual call data)

---

## 🔑 Where to Find Your Twilio Credentials

If you don't have your Twilio credentials:

1. **Go to Twilio Console:** https://console.twilio.com/
2. **Log in** to your Twilio account
3. **Find Account SID and Auth Token:**
   - Click on your account name (top right)
   - Or go to: https://console.twilio.com/us1/develop/runtime/api-keys
   - Copy **Account SID** and **Auth Token**

4. **Find Phone Number:**
   - Go to: https://console.twilio.com/us1/develop/phone-numbers/manage/incoming
   - Find your active phone number
   - Copy the phone number (format: +1XXXXXXXXXX)

---

## 🧪 Verification

After adding the credentials and restarting:

1. **Check backend logs** - Should show no errors about missing Twilio config
2. **Test `/api/twilio/configured`** - Should return `{"configured": true}`
3. **Test `/api/twilio/call-status/summary`** - Should return 200 OK (not 400)

---

## 🐛 Troubleshooting

### Still Getting 400 Error?

1. **Check that variables are set correctly:**
   ```bash
   cat .env | grep TWILIO
   ```

2. **Check for typos:**
   - Variable names must be exactly: `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER`
   - No spaces around `=`
   - No quotes needed (unless values have special characters)

3. **Verify values are correct:**
   - Account SID starts with `AC`
   - Auth Token is a long string
   - Phone number starts with `+` and country code

4. **Make sure server was restarted** after editing `.env`

5. **Check backend logs** for specific error messages

---

## 💡 Security Note

⚠️ **Never commit `.env` to git!** The `.env` file should be in `.gitignore`.

Your `.env` file contains sensitive credentials - keep it secure!

---

## ✅ Success Checklist

- [ ] `.env` file edited on Linode
- [ ] `TWILIO_ACCOUNT_SID` added
- [ ] `TWILIO_AUTH_TOKEN` added
- [ ] `TWILIO_PHONE_NUMBER` added
- [ ] Verified with `cat .env | grep TWILIO`
- [ ] Backend server restarted
- [ ] `/api/twilio/configured` returns `{"configured": true}`
- [ ] `/api/twilio/call-status/summary` returns 200 OK

