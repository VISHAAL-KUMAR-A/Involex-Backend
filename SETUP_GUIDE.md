# PracticePanther Integration Setup Guide

## Step 1: Get PracticePanther API Access

### 1.1 Request API Credentials
1. Contact PracticePanther support or your account manager
2. Request API access for your account
3. Provide your redirect URI: `http://localhost:8000/api/practice-panther/oauth/callback/`
4. You'll receive:
   - `CLIENT_ID`
   - `CLIENT_SECRET`

### 1.2 Find Your PracticePanther User ID
1. Log into your PracticePanther account
2. Go to **Settings** → **Users**
3. Click on your user profile
4. Copy your User ID (you'll need this for configuration)

### 1.3 Get Matter IDs (Optional)
1. Go to **Matters** in PracticePanther
2. Open any matter you want to use as default
3. Copy the Matter ID from the URL or matter details

## Step 2: Configure Environment Variables

Create a `.env` file in your project root:

```bash
# Django Configuration
SECRET_KEY=your-secret-key-here
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1,*

# OpenAI Configuration
OPENAI_API_KEY=your-openai-api-key-here

# PracticePanther API Configuration
PRACTICE_PANTHER_BASE_URL=https://app.practicepanther.com
PRACTICE_PANTHER_CLIENT_ID=your-client-id-from-practicepanther
PRACTICE_PANTHER_CLIENT_SECRET=your-client-secret-from-practicepanther
PRACTICE_PANTHER_REDIRECT_URI=http://localhost:8000/api/practice-panther/oauth/callback/

# Default Settings
DEFAULT_TIME_ENTRY_DURATION_MINUTES=15
DEFAULT_HOURLY_RATE=250.00

# CORS Configuration
CORS_ALLOW_ALL_ORIGINS=True
```

## Step 3: Testing Strategy

### Phase 1: Backend Only Testing
Test the backend API endpoints using Postman/curl before frontend integration.

### Phase 2: OAuth Flow Testing
Test the authentication flow manually.

### Phase 3: Extension Integration
Update your Chrome extension to use the new features.

## Step 4: Frontend Developer Instructions

See the "Frontend Integration Guide" section below for detailed instructions.

---

# Frontend Integration Guide

## Current State: Extension Works Without Authentication

Your existing Chrome extension should continue working exactly as before. The email summarization API doesn't require authentication for basic functionality.

## Phase 1: Basic Integration (No Changes Needed)

Your extension can continue using:

```javascript
// This still works exactly as before
fetch('http://localhost:8000/api/summarize-email/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
        email_content: emailText,
        subject: emailSubject,
        sender_email: senderEmail,
        recipient_email: recipientEmail
    })
})
```

## Phase 2: Add Authentication for PracticePanther Features

### Option A: Simple User Management (Recommended)

Create a simple login system where users enter their Django username/password:

```javascript
// 1. Add login functionality to your extension
async function loginUser(username, password) {
    const response = await fetch('http://localhost:8000/auth/login/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password })
    });
    
    if (response.ok) {
        const data = await response.json();
        // Store token in extension storage
        chrome.storage.local.set({ 'auth_token': data.token });
        return data.token;
    }
    throw new Error('Login failed');
}

// 2. Use token in API calls
async function summarizeEmailWithBilling(emailData) {
    const token = await chrome.storage.local.get('auth_token');
    
    const response = await fetch('http://localhost:8000/api/summarize-email/', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Authorization': token.auth_token ? `Bearer ${token.auth_token}` : undefined
        },
        body: JSON.stringify({
            ...emailData,
            create_time_entry: true  // Enable automatic billing
        })
    });
    
    const result = await response.json();
    
    // Show success message if time entry was created
    if (result.time_entry_created) {
        showNotification(`✅ Time entry created! $${result.time_entry_details.total}`);
    }
    
    return result;
}
```

### Option B: OAuth Flow in Extension (Advanced)

For a more sophisticated approach, implement the PracticePanther OAuth flow directly in the extension.

## Phase 3: Enhanced Features

Add these features to your extension:

### 3.1 Settings Panel
```javascript
// Add settings UI for users to configure:
// - Default duration (15, 30, 45 minutes)
// - Enable/disable automatic billing
// - Select default matter
```

### 3.2 Billing Confirmation
```javascript
// Show confirmation before creating time entries
function showBillingConfirmation(summary, duration, rate) {
    const total = (duration / 60) * rate;
    return confirm(`Create time entry?\nDuration: ${duration}min\nRate: $${rate}/hr\nTotal: $${total.toFixed(2)}`);
}
```

---

# Testing Guide

## Backend Testing (Do This First)

### 1. Test Basic Email Summarization

```bash
curl -X POST http://localhost:8000/api/summarize-email/ \
  -H "Content-Type: application/json" \
  -d '{
    "email_content": "Dear Client, I have reviewed your contract and found several issues...",
    "subject": "Contract Review",
    "create_time_entry": false
  }'
```

Expected: Should return summary without time entry.

### 2. Test User Creation

```bash
# Create a test user via Django admin or shell
python manage.py shell
```

```python
from django.contrib.auth.models import User
user = User.objects.create_user('testlawyer', 'test@law.com', 'password123')
print(f"Created user: {user.id}")
```

### 3. Test OAuth Flow (Manual)

1. Go to: `http://localhost:8000/api/practice-panther/oauth/init/`
2. Should redirect to PracticePanther authorization page
3. After authorization, should redirect back with code
4. Test callback endpoint with the received code

### 4. Test PracticePanther Configuration

```bash
# After OAuth is complete, test configuration
curl -X POST http://localhost:8000/api/practice-panther/config/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "practice_panther_user_id": "your-pp-user-id",
    "default_hourly_rate": 275.00,
    "auto_create_time_entries": true
  }'
```

### 5. Test End-to-End Time Entry Creation

```bash
curl -X POST http://localhost:8000/api/summarize-email/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "email_content": "Dear Client, I completed the contract review...",
    "subject": "Contract Review Complete",
    "duration_minutes": 30,
    "create_time_entry": true
  }'
```

Expected: Should return summary + time entry details.

## Frontend Testing

### 1. Test Extension Without Authentication
Your existing extension should work exactly as before.

### 2. Test Extension With Authentication
After adding login functionality, test that time entries are created.

### 3. Verify in PracticePanther
Log into PracticePanther and verify that time entries appear in your timesheet.

---

# Authentication Implementation

## Simple Approach: Add Django Token Authentication

Add this to your backend:

### 1. Add to settings.py
```python
INSTALLED_APPS = [
    # ... existing apps
    'rest_framework.authtoken',
]

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',
    ],
}
```

### 2. Create migration
```bash
python manage.py makemigrations
python manage.py migrate
```

### 3. Add login endpoint
```python
# In views.py
from rest_framework.authtoken.models import Token
from django.contrib.auth import authenticate

@api_view(['POST'])
def login_view(request):
    username = request.data.get('username')
    password = request.data.get('password')
    
    user = authenticate(username=username, password=password)
    if user:
        token, created = Token.objects.get_or_create(user=user)
        return Response({'token': token.key, 'user_id': user.id})
    
    return Response({'error': 'Invalid credentials'}, status=400)
```

### 4. Add to urls.py
```python
path('auth/login/', login_view, name='login'),
```

---

# Quick Start Checklist

## Backend Setup
- [ ] Get PracticePanther API credentials
- [ ] Add credentials to `.env` file
- [ ] Run `python manage.py migrate`
- [ ] Create test user: `python manage.py createsuperuser`
- [ ] Test basic API with Postman

## Frontend Setup
- [ ] Extension works as-is for basic summarization
- [ ] Add login UI (optional for now)
- [ ] Test with authentication token
- [ ] Add billing success notifications

## Go-Live
- [ ] Test OAuth flow end-to-end
- [ ] Verify time entries appear in PracticePanther
- [ ] Train users on new billing features 