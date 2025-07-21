# Involex Backend - Email Summarization API

A Django REST API designed for lawyers to automatically summarize client emails using OpenAI's GPT model. Perfect for creating billable entries in practice management systems like PracticePanther, Clio, MyCase, etc.

## Features

- 🤖 AI-powered email summarization using OpenAI GPT-3.5-turbo
- ⚖️ Specialized for legal professionals and billing purposes
- 🔗 CORS-enabled for Chrome extension integration
- 📊 Word count analysis (original vs. summary)
- 📝 Auto-formatted billable descriptions
- ⚡ Fast processing with timing metrics

## Setup Instructions

### 1. Clone the Repository

```bash
git clone <your-repo-url>
cd Involex_Backend
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Environment Configuration

Copy the example environment file and add your API key:

```bash
# Copy the example file
cp .env.example .env
```

Then edit `.env` and add your OpenAI API key:

```env
# OpenAI Configuration
OPENAI_API_KEY=your-actual-openai-api-key-here
```

### 4. Run Database Migrations

```bash
python manage.py migrate
```

### 5. Start the Development Server

```bash
python manage.py runserver
```

The API will be available at: `http://localhost:8000/`

## API Endpoints

### Email Summarization
- **URL**: `/api/summarize-email/`
- **Method**: `POST`
- **Content-Type**: `application/json`

### Request Body

```json
{
    "email_content": "Dear Client, I have reviewed your contract and found several issues that need to be addressed before signing...",
    "sender_email": "lawyer@lawfirm.com",
    "recipient_email": "client@company.com",
    "subject": "Contract Review Update"
}
```

**Required Fields:**
- `email_content` (string): The full content of the email to be summarized

**Optional Fields:**
- `sender_email` (string): Email address of the sender
- `recipient_email` (string): Email address of the recipient
- `subject` (string): Subject line of the email

### Response

```json
{
    "summary": "Reviewed client contract and identified several issues requiring attention before execution. Provided recommendations for contract modifications and next steps for resolution.",
    "word_count_original": 150,
    "word_count_summary": 25,
    "billable_description": "Email correspondence with client@company.com regarding Contract Review Update. Reviewed client contract and identified several issues requiring attention before execution. Provided recommendations for contract modifications and next steps for resolution.",
    "processing_time": 2.45
}
```

## Testing with Postman

### Step 1: Create a New Request
1. Open Postman
2. Click "New" → "Request"
3. Name it "Email Summary Test"

### Step 2: Configure the Request
1. **Method**: Select `POST`
2. **URL**: `http://localhost:8000/api/summarize-email/`
3. **Headers**: 
   - Key: `Content-Type`, Value: `application/json`

### Step 3: Add Request Body
1. Go to the "Body" tab
2. Select "raw" and "JSON"
3. Paste this example:

```json
{
    "email_content": "Dear Mr. Johnson, I have completed the review of your employment contract dated March 15, 2024. After careful analysis, I have identified several areas that require modification to better protect your interests. Specifically, the non-compete clause in Section 4.2 is overly broad and may not be enforceable in our jurisdiction. I recommend we negotiate to limit the geographical scope to the immediate metropolitan area and reduce the time period from 24 months to 12 months. Additionally, the intellectual property provisions in Section 6 need clarification regarding work done outside of business hours. I have prepared a marked-up version of the contract with my recommendations and will send it under separate cover. Please review my comments and let me know if you would like to schedule a call to discuss the proposed changes before I reach out to opposing counsel. I anticipate this negotiation process will take approximately 2-3 weeks to complete.",
    "sender_email": "sarah.attorney@lawfirm.com",
    "recipient_email": "client@company.com",
    "subject": "Employment Contract Review - Action Items"
}
```

### Step 4: Send the Request
1. Click "Send"
2. You should receive a JSON response with the summary and billing information

### Alternative Test with Minimal Data
```json
{
    "email_content": "Dear Client, I have reviewed your case files and prepared the motion for summary judgment. The deadline for filing is next Friday. Please review the attached draft and provide your feedback by Wednesday so I can incorporate any changes before submission."
}
```

## Chrome Extension Integration

The API is configured with CORS headers to work with Chrome extensions:

```javascript
// Example Chrome extension usage
fetch('http://localhost:8000/api/summarize-email/', {
    method: 'POST',
    headers: {
        'Content-Type': 'application/json',
    },
    body: JSON.stringify({
        email_content: emailText,
        sender_email: senderEmail,
        recipient_email: recipientEmail,
        subject: emailSubject
    })
})
.then(response => response.json())
.then(data => {
    // Use data.billable_description for practice management systems
    console.log('Billable Entry:', data.billable_description);
});
```

## Error Handling

The API returns appropriate HTTP status codes:

- `200 OK`: Successful summarization
- `400 Bad Request`: Invalid input data
- `502 Bad Gateway`: OpenAI API error
- `500 Internal Server Error`: Server error

Example error response:
```json
{
    "error": "Invalid input data",
    "details": {
        "email_content": ["This field is required."]
    }
}
```

## Security Notes

- The OpenAI API key is configured in `settings.py`
- For production, move sensitive keys to environment variables
- CSRF protection is disabled for API endpoints
- CORS is set to allow all origins for development

## Practice Management Integration

The `billable_description` field in the response is specifically formatted for easy integration with:
- PracticePanther
- Clio
- MyCase
- TimeSolv
- And other legal practice management systems

Simply use the `billable_description` as the entry description and add appropriate time/rate information for your billable entries. 