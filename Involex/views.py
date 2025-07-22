from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings
import openai
import time
from .serializers import EmailSummarySerializer, EmailSummaryResponseSerializer

# Add debugging imports
import json
import logging
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

# Set up logging
logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name='dispatch')  # Add this for CSRF exemption
class EmailSummaryAPIView(APIView):
    """
    API View to summarize emails using OpenAI GPT model.
    Specifically designed for lawyers to create billable entries.
    """

    def post(self, request):
        start_time = time.time()

        # Validate input data
        serializer = EmailSummarySerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"error": "Invalid input data", "details": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )

        validated_data = serializer.validated_data
        email_content = validated_data['email_content']
        sender_email = validated_data.get('sender_email', '')
        recipient_email = validated_data.get('recipient_email', '')
        subject = validated_data.get('subject', '')

        try:
            # Initialize OpenAI client
            client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)

            # Create the prompt for legal email summarization
            prompt = self._create_legal_summary_prompt(
                email_content, sender_email, recipient_email, subject
            )

            # Call OpenAI API
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a legal assistant helping lawyers create concise, professional summaries of client communications for billing purposes."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                max_tokens=500,
                temperature=0.3
            )

            summary = response.choices[0].message.content.strip()

            # Calculate word counts
            original_word_count = len(email_content.split())
            summary_word_count = len(summary.split())

            # Create billable description
            billable_description = self._create_billable_description(
                summary, sender_email, recipient_email, subject
            )

            processing_time = time.time() - start_time

            # Prepare response
            response_data = {
                "summary": summary,
                "word_count_original": original_word_count,
                "word_count_summary": summary_word_count,
                "billable_description": billable_description,
                "processing_time": round(processing_time, 2)
            }

            # Validate response data
            response_serializer = EmailSummaryResponseSerializer(
                data=response_data)
            if response_serializer.is_valid():
                return Response(response_serializer.data, status=status.HTTP_200_OK)
            else:
                return Response(
                    {"error": "Response validation failed",
                        "details": response_serializer.errors},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

        except openai.OpenAIError as e:
            return Response(
                {"error": "OpenAI API error", "details": str(e)},
                status=status.HTTP_502_BAD_GATEWAY
            )
        except Exception as e:
            return Response(
                {"error": "Internal server error", "details": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def _create_legal_summary_prompt(self, email_content, sender_email, recipient_email, subject):
        """Create a specialized prompt for legal email summarization"""
        prompt = f"""
Please summarize the following email for legal billing purposes. The summary should be:
1. Professional and concise
2. Include key legal matters discussed
3. Mention any action items or next steps
4. Be suitable for client billing records
5. Focus on the substantive legal content

Email Details:
Subject: {subject}
From: {sender_email}
To: {recipient_email}

Email Content:
{email_content}

Please provide a concise professional summary (2-3 sentences) that captures the essential legal communication for billing purposes.
"""
        return prompt

    def _create_billable_description(self, summary, sender_email, recipient_email, subject):
        """Create a formatted billable entry description"""
        if sender_email and recipient_email:
            parties = f"Email correspondence with {recipient_email if sender_email else 'client'}"
        else:
            parties = "Email correspondence"

        subject_text = f" regarding {subject}" if subject else ""

        billable_description = f"{parties}{subject_text}. {summary}"

        return billable_description

    def options(self, request, *args, **kwargs):
        """Handle CORS preflight requests"""
        return Response({'status': 'ok'}, status=status.HTTP_200_OK)

    def get(self, request):
        """GET method to provide API documentation"""
        return Response({
            "message": "Email Summary API for Legal Professionals",
            "description": "POST email content to receive AI-powered summaries for billing purposes",
            "endpoint": "/api/summarize-email/",
            "method": "POST",
            "required_fields": ["email_content"],
            "optional_fields": ["sender_email", "recipient_email", "subject"],
            "example_request": {
                "email_content": "Dear Client, I have reviewed your contract...",
                "sender_email": "lawyer@lawfirm.com",
                "recipient_email": "client@company.com",
                "subject": "Contract Review Update"
            }
        })


# DEBUG VIEW - Remove after debugging
@csrf_exempt
def summarize_email_debug_view(request):
    """
    Temporary debugging view for email summarization
    """
    # Add extensive debugging
    logger.info(f"🔧 DEBUG: Request method: {request.method}")
    logger.info(f"🔧 DEBUG: Request headers: {dict(request.headers)}")
    logger.info(f"🔧 DEBUG: Request content type: {request.content_type}")
    logger.info(f"🔧 DEBUG: Request body (raw): {request.body}")

    if request.method == 'POST':
        try:
            # Try to parse JSON
            if request.content_type == 'application/json':
                data = json.loads(request.body)
                logger.info(f"🔧 DEBUG: Parsed JSON data: {data}")

                # Check required fields
                required_fields = ['email_content',
                                   'sender_email', 'recipient_email', 'subject']
                missing_fields = [
                    field for field in required_fields if field not in data or not data[field]]

                if missing_fields:
                    logger.error(
                        f"🔧 DEBUG: Missing required fields: {missing_fields}")
                    return JsonResponse({
                        'error': f'Missing required fields: {missing_fields}',
                        'received_data': data
                    }, status=400)

                logger.info(f"✅ DEBUG: All required fields present")
                logger.info(
                    f"🔧 DEBUG: Email content: {data['email_content'][:100]}...")

                # Your existing summarization logic here...
                # For now, return a test response
                return JsonResponse({
                    'summary': f"DEBUG: Received email from {data['sender_email']} to {data['recipient_email']} about {data['subject']}",
                    'word_count_original': len(data['email_content'].split()),
                    'word_count_summary': 15,
                    'billable_description': f"Email analysis for {data['subject']}",
                    'processing_time': 0.5
                })

            else:
                logger.error(
                    f"🔧 DEBUG: Invalid content type: {request.content_type}")
                return JsonResponse({'error': f'Invalid content type: {request.content_type}'}, status=400)

        except json.JSONDecodeError as e:
            logger.error(f"🔧 DEBUG: JSON decode error: {e}")
            logger.error(f"🔧 DEBUG: Request body: {request.body}")
            return JsonResponse({'error': f'Invalid JSON: {e}'}, status=400)

        except Exception as e:
            logger.error(f"🔧 DEBUG: Unexpected error: {e}")
            return JsonResponse({'error': f'Server error: {e}'}, status=500)

    elif request.method == 'OPTIONS':
        # Handle CORS preflight
        return JsonResponse({'status': 'ok'})

    else:
        return JsonResponse({'error': 'Method not allowed'}, status=405)
