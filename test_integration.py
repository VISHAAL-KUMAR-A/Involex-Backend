#!/usr/bin/env python
"""
Test script to verify PracticePanther integration is working
Run this after setting up your backend to test all functionality
"""

import requests
import json
import os
import sys

# Configuration
BASE_URL = "http://localhost:8000/api"
TEST_USER = {
    "username": "testlawyer",
    "password": "testpass123",
    "email": "test@lawfirm.com"
}


def test_server_status():
    """Test if the Django server is running"""
    print("🔍 Testing server status...")
    try:
        response = requests.get(f"{BASE_URL}/summarize-email/")
        if response.status_code == 200:
            print("✅ Server is running and responding")
            return True
        else:
            print(f"❌ Server responded with status {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print("❌ Server is not running. Please start with: python manage.py runserver")
        return False


def test_basic_email_summarization():
    """Test basic email summarization without authentication"""
    print("\n🔍 Testing basic email summarization...")

    test_email = {
        "email_content": "Dear Client, I have completed the review of your employment contract. The non-compete clause needs revision as it's too broad. I recommend limiting it to 12 months and local area only. Please schedule a call to discuss the proposed changes.",
        "subject": "Contract Review Complete",
        "sender_email": "lawyer@firm.com",
        "recipient_email": "client@company.com",
        "create_time_entry": False
    }

    try:
        response = requests.post(f"{BASE_URL}/summarize-email/",
                                 json=test_email,
                                 headers={"Content-Type": "application/json"})

        if response.status_code == 200:
            data = response.json()
            print("✅ Email summarization working!")
            print(f"   Summary: {data['summary'][:100]}...")
            print(
                f"   Billable Description: {data['billable_description'][:100]}...")
            print(f"   Processing Time: {data['processing_time']}s")
            return True
        else:
            print(f"❌ Email summarization failed: {response.status_code}")
            print(f"   Error: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error testing email summarization: {str(e)}")
        return False


def test_user_registration():
    """Test user registration"""
    print("\n🔍 Testing user registration...")

    try:
        response = requests.post(f"{BASE_URL}/auth/register/",
                                 json=TEST_USER,
                                 headers={"Content-Type": "application/json"})

        if response.status_code == 201:
            data = response.json()
            print("✅ User registration working!")
            print(f"   Token: {data['token'][:20]}...")
            return data['token']
        elif response.status_code == 400 and "already exists" in response.text:
            print("ℹ️  User already exists, trying login...")
            return test_user_login()
        else:
            print(f"❌ User registration failed: {response.status_code}")
            print(f"   Error: {response.text}")
            return None
    except Exception as e:
        print(f"❌ Error testing user registration: {str(e)}")
        return None


def test_user_login():
    """Test user login"""
    print("\n🔍 Testing user login...")

    try:
        response = requests.post(f"{BASE_URL}/auth/login/",
                                 json={
                                     "username": TEST_USER["username"], "password": TEST_USER["password"]},
                                 headers={"Content-Type": "application/json"})

        if response.status_code == 200:
            data = response.json()
            print("✅ User login working!")
            print(f"   Token: {data['token'][:20]}...")
            print(f"   Username: {data['username']}")
            print(f"   Has PP Config: {data['has_practice_panther_config']}")
            print(f"   Has PP Token: {data['has_practice_panther_token']}")
            return data['token']
        else:
            print(f"❌ User login failed: {response.status_code}")
            print(f"   Error: {response.text}")
            return None
    except Exception as e:
        print(f"❌ Error testing user login: {str(e)}")
        return None


def test_authenticated_email_summarization(token):
    """Test email summarization with authentication"""
    print("\n🔍 Testing authenticated email summarization...")

    test_email = {
        "email_content": "Dear Client, I have completed the review of your employment contract. The non-compete clause needs revision as it's too broad. I recommend limiting it to 12 months and local area only. Please schedule a call to discuss the proposed changes.",
        "subject": "Contract Review Complete",
        "sender_email": "lawyer@firm.com",
        "recipient_email": "client@company.com",
        "create_time_entry": True,  # This will try to create time entry
        "duration_minutes": 20
    }

    try:
        response = requests.post(f"{BASE_URL}/summarize-email/",
                                 json=test_email,
                                 headers={
                                     "Content-Type": "application/json",
                                     "Authorization": f"Token {token}"
                                 })

        if response.status_code == 200:
            data = response.json()
            print("✅ Authenticated email summarization working!")
            print(f"   Summary: {data['summary'][:100]}...")
            print(f"   Time Entry Created: {data['time_entry_created']}")
            if data['time_entry_created']:
                print(f"   Time Entry Details: {data['time_entry_details']}")
            else:
                print("   ℹ️  Time entry not created (PracticePanther not configured)")
            return True
        else:
            print(
                f"❌ Authenticated email summarization failed: {response.status_code}")
            print(f"   Error: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error testing authenticated email summarization: {str(e)}")
        return False


def test_user_status(token):
    """Test user status endpoint"""
    print("\n🔍 Testing user status...")

    try:
        response = requests.get(f"{BASE_URL}/auth/status/",
                                headers={"Authorization": f"Token {token}"})

        if response.status_code == 200:
            data = response.json()
            print("✅ User status endpoint working!")
            print(f"   User: {data['user']['username']}")
            print(
                f"   PP Configured: {data['practice_panther']['configured']}")
            return True
        else:
            print(f"❌ User status failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Error testing user status: {str(e)}")
        return False


def main():
    """Run all tests"""
    print("🚀 Starting PracticePanther Integration Tests\n")

    # Test 1: Server Status
    if not test_server_status():
        print("\n❌ Server is not running. Please start the Django server first.")
        sys.exit(1)

    # Test 2: Basic Email Summarization
    if not test_basic_email_summarization():
        print("\n❌ Basic email summarization is not working. Check your OpenAI API key.")
        sys.exit(1)

    # Test 3: User Registration/Login
    token = test_user_registration()
    if not token:
        print("\n❌ Authentication system is not working.")
        sys.exit(1)

    # Test 4: Authenticated Email Summarization
    test_authenticated_email_summarization(token)

    # Test 5: User Status
    test_user_status(token)

    print("\n" + "="*60)
    print("🎉 BASIC INTEGRATION TESTS COMPLETE!")
    print("="*60)
    print()
    print("✅ Your backend is ready for Chrome extension integration!")
    print()
    print("📋 NEXT STEPS:")
    print("1. Get PracticePanther API credentials")
    print("2. Add them to your .env file")
    print("3. Test OAuth flow manually")
    print("4. Update your Chrome extension to use authentication")
    print()
    print("🔧 Frontend Developer Instructions:")
    print("- Extension works as-is for basic summarization")
    print("- Add login UI for PracticePanther features")
    print("- Use token authentication for API calls")
    print("- Test with the sample code in SETUP_GUIDE.md")


if __name__ == "__main__":
    main()
