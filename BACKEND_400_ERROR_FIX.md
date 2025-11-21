# Fix: 400 Bad Request on `/api/twilio/call-status/summary`

## 🔴 The Problem

Your backend logs show:
```
INFO:     124.123.119.85:38118 - "GET /api/twilio/call-status/summary?limit=15 HTTP/1.1" 400 Bad Request
```

This happens when the `TwilioCallManager` cannot be created, even though `/api/twilio/configured` returns `True`.

## ✅ Solution

The backend code has been updated with better error handling. You need to:

### Step 1: Update Backend Code on Linode

1. **SSH into your Linode server:**
   ```bash
   ssh your-user@172.105.50.83
   ```

2. **Navigate to your VOCA project:**
   ```bash
   cd ~/voca-2.0
   # or wherever your project is
   ```

3. **Pull the latest code or manually update `src/voca/api.py`:**
   
   The file has been updated with better error handling. You can either:
   - Pull from git if you're using version control
   - Or manually copy the updated code (I've improved error messages)

4. **Restart the backend server:**
   ```bash
   # Stop the current server (Ctrl+C)
   # Then restart:
   python main_api_server.py
   ```

### Step 2: Check Backend Logs

After restarting, when you see the 400 error, check the logs. You should now see a more detailed error message like:

- `"Twilio not configured. Please set up environment variables (TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER)."` - Missing env vars
- `"Twilio configuration is valid but manager failed to initialize. Check server logs for details."` - Initialization failed

### Step 3: Verify Environment Variables on Linode

Check that all required Twilio environment variables are set:

```bash
# SSH into Linode, then:
cd ~/voca-2.0
cat .env
# or
env | grep TWILIO
```

You should see:
```env
TWILIO_ACCOUNT_SID=your_account_sid
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_PHONE_NUMBER=+1XXXXXXXXXX
```

**Important:** Make sure these are set in your `.env` file on Linode.

### Step 4: Check for Initialization Errors

The improved code will now log errors when creating `TwilioCallManager`. Check your backend logs for:

```
ERROR - Failed to create TwilioCallManager: <error message>
```

This will tell you what's actually failing.

## 🧪 Testing

1. **Test Twilio configuration:**
   ```bash
   curl http://172.105.50.83:8000/api/twilio/configured
   ```
   Should return: `{"configured": true}`

2. **Test call status summary:**
   ```bash
   curl http://172.105.50.83:8000/api/twilio/call-status/summary?limit=15
   ```
   
   - ✅ **200 OK**: Should return call status summary
   - ❌ **400 Bad Request**: Check the error message in the response
   - ❌ **500 Internal Server Error**: Check backend logs

## 🐛 Common Issues

### Issue 1: Missing Environment Variables

**Symptom:** `/api/twilio/configured` returns `False` or the 400 error says "Twilio not configured"

**Solution:**
1. Create/update `.env` file on Linode:
   ```bash
   nano ~/voca-2.0/.env
   ```
2. Add:
   ```env
   TWILIO_ACCOUNT_SID=your_account_sid
   TWILIO_AUTH_TOKEN=your_auth_token
   TWILIO_PHONE_NUMBER=+1XXXXXXXXXX
   ```
3. Restart backend server

### Issue 2: Invalid Twilio Credentials

**Symptom:** `/api/twilio/configured` returns `True` but `/api/twilio/call-status/summary` returns 400

**Solution:**
1. Verify credentials in Twilio Console
2. Check that credentials are correct in `.env`
3. Try making a test API call from Linode:
   ```bash
   python -c "from src.voca.twilio_config import get_twilio_config; config = get_twilio_config(); print('Valid:', config.validate())"
   ```

### Issue 3: Twilio Client Initialization Fails

**Symptom:** Error logs show "Failed to create TwilioCallManager"

**Solution:**
- Check that Twilio Python library is installed: `pip install twilio`
- Verify network connectivity from Linode to Twilio API
- Check backend logs for specific error message

## 📝 What Changed

The backend code now:
1. ✅ Better error messages when Twilio is not configured
2. ✅ Distinguishes between "not configured" and "initialization failed"
3. ✅ Logs errors when creating TwilioCallManager fails
4. ✅ Provides specific environment variable names in error messages

## 🎯 Next Steps

1. ✅ Update backend code on Linode (if you haven't already)
2. ✅ Restart backend server
3. ✅ Check backend logs for specific error messages
4. ✅ Verify environment variables are set correctly
5. ✅ Test the endpoint again

## 💡 Still Having Issues?

Check the backend logs for:
- `ERROR - Failed to create TwilioCallManager: <error>`
- Any stack traces related to Twilio
- Environment variable loading issues

Share the specific error message from the logs, and I can help troubleshoot further!

