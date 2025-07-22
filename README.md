# Involex Backend - Email Summarization with PracticePanther Integration

A Django REST API that provides AI-powered email summarization specifically designed for legal professionals, with automatic billable time entry creation in PracticePanther.

## Features

- **AI-Powered Email Summarization**: Uses OpenAI GPT to create professional legal summaries
- **PracticePanther Integration**: Automatically creates billable time entries
- **OAuth 2.0 Authentication**: Secure connection to PracticePanther
- **Flexible Time Tracking**: Customizable duration and hourly rates
- **Matter Management**: Link time entries to specific matters
- **Chrome Extension Ready**: CORS configured for browser extensions

## Quick Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Environment Configuration

Copy `.env.example` to `.env` and configure your settings:

```bash
# Django Configuration
SECRET_KEY=your-secret-key-here
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1,*

# OpenAI Configuration
OPENAI_API_KEY=your-openai-api-key-here

# PracticePanther API Configuration
PRACTICE_PANTHER_CLIENT_ID=your-client-id
PRACTICE_PANTHER_CLIENT_SECRET=your-client-secret
PRACTICE_PANTHER_REDIRECT_URI=http://localhost:8000/api/practice-panther/oauth/callback/

# Default Settings
DEFAULT_TIME_ENTRY_DURATION_MINUTES=15
DEFAULT_HOURLY_RATE=250.00
```

### 3. Database Setup

```bash
python manage.py migrate
python manage.py createsuperuser
```

### 4. Run Server

```bash
python manage.py runserver
```

## PracticePanther API Setup

### 1. Request API Access

1. Submit a request for API access to PracticePanther
2. Receive your `CLIENT_ID` and `CLIENT_SECRET`
3. Configure your redirect URI in PracticePanther's developer settings

### 2. OAuth Flow

The integration uses OAuth 2.0 for secure authentication:

1. **Initialize OAuth**: `GET /api/practice-panther/oauth/init/`
2. **User Authorization**: Redirect to PracticePanther
3. **Handle Callback**: `POST /api/practice-panther/oauth/callback/`
4. **Token Management**: Automatic refresh handling

## API Endpoints

### Email Summarization

#### `POST /api/summarize-email/`

Summarize an email and optionally create a time entry.

**Request Body:**
```json
{
  "email_content": "Dear Client, I have reviewed your contract...",
  "sender_email": "lawyer@lawfirm.com",
  "recipient_email": "client@company.com",
  "subject": "Contract Review Update",
  "duration_minutes": 15,
  "matter_id": "12345",
  "create_time_entry": true
}
```

**Response:**
```json
{
  "summary": "Reviewed client contract and identified key issues...",
  "word_count_original": 250,
  "word_count_summary": 45,
  "billable_description": "Email correspondence with client@company.com regarding Contract Review Update. Reviewed client contract and identified key issues...",
  "processing_time": 1.23,
  "time_entry_created": true,
  "time_entry_details": {
    "time_entry_id": "pp-12345",
    "hours": 0.25,
    "rate": 250.00,
    "total": 62.50
  }
}
```

### PracticePanther OAuth

#### `GET /api/practice-panther/oauth/init/`
Initialize OAuth flow (requires authentication).

#### `POST /api/practice-panther/oauth/callback/`
Handle OAuth callback with authorization code.

### Configuration

#### `GET /api/practice-panther/config/`
Get user's PracticePanther configuration.

#### `POST /api/practice-panther/config/`
Set up PracticePanther configuration:

```json
{
  "practice_panther_user_id": "user123",
  "default_matter_id": "matter456",
  "default_hourly_rate": 275.00,
  "auto_create_time_entries": true
}
```

### Matter Management

#### `GET /api/practice-panther/matters/`
Get list of available matters from PracticePanther.

### Time Entry Management

#### `GET /api/time-entries/`
List all time entries created from email summaries.

#### `POST /api/time-entries/create/`
Create a standalone time entry:

```json
{
  "description": "Research case law for client matter",
  "duration_minutes": 30,
  "matter_id": "matter123",
  "hourly_rate": 250.00
}
```

## Usage Examples

### Basic Email Summarization (No Authentication Required)

```python
import requests

response = requests.post('http://localhost:8000/api/summarize-email/', json={
    "email_content": "Dear Client, I have completed the contract review...",
    "subject": "Contract Review Complete",
    "create_time_entry": False  # Don't create time entry
})

summary_data = response.json()
print(summary_data['summary'])
```

### With PracticePanther Integration

```python
# 1. First authenticate user and set up PracticePanther connection
# 2. Then summarize email with automatic time entry creation

response = requests.post('http://localhost:8000/api/summarize-email/', 
    json={
        "email_content": "Dear Client, I have completed the contract review...",
        "subject": "Contract Review Complete",
        "duration_minutes": 20,
        "matter_id": "matter123",
        "create_time_entry": True
    },
    headers={'Authorization': 'Bearer your-token-here'}
)

result = response.json()
if result['time_entry_created']:
    print(f"Time entry created: {result['time_entry_details']['time_entry_id']}")
    print(f"Billable amount: ${result['time_entry_details']['total']}")
```

### Chrome Extension Integration

```javascript
// From your Chrome extension
fetch('http://localhost:8000/api/summarize-email/', {
    method: 'POST',
    headers: {
        'Content-Type': 'application/json',
    },
    body: JSON.stringify({
        email_content: emailText,
        subject: emailSubject,
        sender_email: senderEmail,
        recipient_email: recipientEmail,
        duration_minutes: 15,
        create_time_entry: true
    })
})
.then(response => response.json())
.then(data => {
    console.log('Summary:', data.summary);
    if (data.time_entry_created) {
        console.log('Time entry created in PracticePanther!');
    }
});
```

## Admin Interface

Access the Django admin at `http://localhost:8000/admin/` to manage:

- **PracticePanther Tokens**: OAuth tokens and expiration
- **PracticePanther Users**: User configurations and settings
- **Email Summary Time Entries**: All created time entries and sync status

## Error Handling

The API includes comprehensive error handling:

- **OpenAI API errors**: Graceful handling of rate limits and API issues
- **PracticePanther sync failures**: Local storage with error logging
- **Authentication errors**: Clear error messages for OAuth issues
- **Validation errors**: Detailed field-level validation feedback

## Security Features

- **OAuth 2.0**: Secure token-based authentication
- **Token refresh**: Automatic token renewal
- **CORS configuration**: Secure cross-origin requests
- **Input validation**: Comprehensive request validation
- **Error logging**: Detailed logging for debugging

## Development

### Running Tests

```bash
python manage.py test
```

### Making Migrations

```bash
python manage.py makemigrations
python manage.py migrate
```

### Debugging

Enable the debug endpoint for testing:

```bash
# Test endpoint available at /api/debug-summarize-email/
```

## Troubleshooting

### Common Issues

1. **PracticePanther API Access**: Ensure you have requested and received API credentials
2. **OAuth Redirect URI**: Must match exactly in PracticePanther settings
3. **Token Expiration**: Tokens are automatically refreshed, but check logs for issues
4. **CORS Issues**: Verify CORS settings for Chrome extension integration

### Logs

Check Django logs for detailed error information:

```bash
# In development, logs output to console
python manage.py runserver --verbosity=2
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Submit a pull request

## License

This project is proprietary software. All rights reserved. 