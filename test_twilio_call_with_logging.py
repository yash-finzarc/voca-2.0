#!/usr/bin/env python3
"""
Test script to make a Twilio call with detailed logging.
This script helps debug WebSocket connection issues by making a test call
and logging all relevant information.
"""

import os
import sys
import time
import logging
import requests
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

def test_twilio_call(test_phone_number=None):
    """Make a test Twilio call and log all details."""
    
    # Get Twilio credentials from environment
    account_sid = os.getenv('TWILIO_ACCOUNT_SID')
    auth_token = os.getenv('TWILIO_AUTH_TOKEN')
    phone_number = os.getenv('TWILIO_PHONE_NUMBER')
    twiml_bin_url = os.getenv('TWILIO_TWIML_BIN_URL_OUTBOUND')
    
    # Test phone number (use your own for testing)
    test_phone = test_phone_number or "+919540465263"  # Default or from command line
    
    logger.info("=" * 80)
    logger.info("TWILIO CALL TEST WITH LOGGING")
    logger.info("=" * 80)
    
    # Verify credentials
    if not account_sid:
        logger.error("❌ TWILIO_ACCOUNT_SID not found in environment variables")
        return False
    
    if not auth_token:
        logger.error("❌ TWILIO_AUTH_TOKEN not found in environment variables")
        return False
    
    if not phone_number:
        logger.error("❌ TWILIO_PHONE_NUMBER not found in environment variables")
        return False
    
    if not twiml_bin_url:
        logger.error("❌ TWILIO_TWIML_BIN_URL_OUTBOUND not found in environment variables")
        return False
    
    logger.info(f"✓ Account SID: {account_sid[:10]}...")
    logger.info(f"✓ From Number: {phone_number}")
    logger.info(f"✓ To Number: {test_phone}")
    logger.info(f"✓ TwiML Bin URL: {twiml_bin_url}")
    logger.info("")
    
    # Make the call
    url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Calls.json"
    
    data = {
        'From': phone_number,
        'To': test_phone,
        'Url': twiml_bin_url,
        'Method': 'GET',
        'StatusCallbackMethod': 'POST',
        'StatusCallback': 'https://voca-2.duckdns.org/webhook/voice',  # Optional: callback URL
    }
    
    logger.info("=" * 80)
    logger.info("MAKING CALL...")
    logger.info("=" * 80)
    logger.info(f"Request URL: {url}")
    logger.info(f"Request Data: {data}")
    logger.info("")
    
    try:
        response = requests.post(
            url,
            auth=(account_sid, auth_token),
            data=data,
            timeout=30
        )
        
        logger.info(f"Response Status Code: {response.status_code}")
        logger.info(f"Response Headers: {dict(response.headers)}")
        logger.info("")
        
        if response.status_code == 201:
            call_data = response.json()
            call_sid = call_data.get('sid')
            
            logger.info("=" * 80)
            logger.info("✅ CALL INITIATED SUCCESSFULLY")
            logger.info("=" * 80)
            logger.info(f"Call SID: {call_sid}")
            logger.info(f"Status: {call_data.get('status')}")
            logger.info(f"Direction: {call_data.get('direction')}")
            logger.info(f"From: {call_data.get('from')}")
            logger.info(f"To: {call_data.get('to')}")
            logger.info("")
            
            # Monitor call status
            logger.info("=" * 80)
            logger.info("MONITORING CALL STATUS...")
            logger.info("=" * 80)
            logger.info("Waiting for WebSocket connection (check server logs)...")
            logger.info("")
            
            # Check call status every 2 seconds for 30 seconds
            for i in range(15):
                time.sleep(2)
                status_url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Calls/{call_sid}.json"
                try:
                    status_response = requests.get(
                        status_url,
                        auth=(account_sid, auth_token),
                        timeout=10
                    )
                    if status_response.status_code == 200:
                        status_data = status_response.json()
                        call_status = status_data.get('status')
                        duration = status_data.get('duration')
                        
                        logger.info(f"[{i*2}s] Call Status: {call_status}" + (f", Duration: {duration}s" if duration else ""))
                        
                        if call_status in ['completed', 'failed', 'busy', 'no-answer', 'canceled']:
                            logger.info("")
                            logger.info(f"Call ended with status: {call_status}")
                            if duration:
                                logger.info(f"Call duration: {duration} seconds")
                            break
                except Exception as e:
                    logger.warning(f"Error checking call status: {e}")
            
            logger.info("")
            logger.info("=" * 80)
            logger.info("TEST COMPLETE")
            logger.info("=" * 80)
            logger.info("")
            logger.info("Next steps:")
            logger.info("1. Check server logs for [CUSTOM_LLM_PIPELINE] messages")
            logger.info("2. Check server logs for [WEBSOCKET_DEBUG] messages")
            logger.info("3. Check Twilio Console -> Monitor -> Logs -> Calls for errors")
            logger.info(f"4. Call SID: {call_sid}")
            logger.info("")
            
            return True
        else:
            logger.error("=" * 80)
            logger.error("❌ CALL FAILED")
            logger.error("=" * 80)
            logger.error(f"Status Code: {response.status_code}")
            logger.error(f"Response: {response.text}")
            return False
            
    except requests.exceptions.RequestException as e:
        logger.error("=" * 80)
        logger.error("❌ ERROR MAKING CALL")
        logger.error("=" * 80)
        logger.error(f"Error: {e}", exc_info=True)
        return False
    except Exception as e:
        logger.error("=" * 80)
        logger.error("❌ UNEXPECTED ERROR")
        logger.error("=" * 80)
        logger.error(f"Error: {e}", exc_info=True)
        return False


if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("Twilio Call Test Script with Detailed Logging")
    print("=" * 80)
    print("")
    print("This script will:")
    print("1. Make a test call using your Twilio credentials")
    print("2. Log all request/response details")
    print("3. Monitor call status")
    print("4. Provide debugging information")
    print("")
    
    # Allow user to specify test phone number
    test_phone_arg = sys.argv[1] if len(sys.argv) > 1 else None
    if test_phone_arg:
        logger.info(f"Using test phone number from command line: {test_phone_arg}")
    
    success = test_twilio_call(test_phone_arg)
    
    sys.exit(0 if success else 1)

