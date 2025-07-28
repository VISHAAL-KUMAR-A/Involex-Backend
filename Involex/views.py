from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings
import openai
import time
from datetime import datetime
from .serializers import EmailSummarySerializer, EmailSummaryResponseSerializer
from .services import ClioAPIService

# Add debugging imports
import json
import logging
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

# Set up logging
logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name='dispatch')
class EmailSummaryAPIView(APIView):
    """
    API View to summarize emails using OpenAI GPT model and create Clio billable entries.
    """

    def post(self, request):
        logger.info(f"🔧 DEBUG: POST request received")
        logger.info(f"🔧 DEBUG: Request headers: {dict(request.headers)}")
        logger.info(f"🔧 DEBUG: Request body: {request.body[:500]}...")

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
        # New field for Clio matter ID
        matter_id = validated_data.get('matter_id')

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

            # Create Clio time entry if matter_id is provided
            clio_entry = None
            if matter_id and sender_email:
                try:
                    clio_service = ClioAPIService(sender_email)
                    # Assuming 6 minutes (360 seconds) for email communication
                    clio_entry = clio_service.create_time_entry(
                        matter_id=matter_id,
                        date=datetime.now(),
                        duration=360,  # 6 minutes in seconds
                        description=billable_description,
                        # First 500 chars as note
                        note=f"Original email content:\n{email_content[:500]}..."
                    )
                except Exception as e:
                    logger.error(f"Failed to create Clio entry: {str(e)}")
                    # Don't fail the whole request if Clio integration fails
                    pass

            processing_time = time.time() - start_time

            # Prepare response
            response_data = {
                "summary": summary,
                "word_count_original": original_word_count,
                "word_count_summary": summary_word_count,
                "billable_description": billable_description,
                "processing_time": round(processing_time, 2),
                "clio_entry_created": bool(clio_entry)
            }

            # Validate response data
            response_serializer = EmailSummaryResponseSerializer(
                data=response_data)
            if response_serializer.is_valid():
                return Response(response_serializer.data, status=status.HTTP_200_OK)
            else:
                return Response(
                    {"error": "Invalid response data",
                        "details": response_serializer.errors},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

        except Exception as e:
            logger.error(f"Error processing request: {str(e)}")
            return Response(
                {"error": "Failed to process email",
                    "details": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def _create_legal_summary_prompt(self, email_content, sender_email, recipient_email, subject):
        """Create a prompt for legal email summarization"""
        context = []
        if sender_email:
            context.append(f"From: {sender_email}")
        if recipient_email:
            context.append(f"To: {recipient_email}")
        if subject:
            context.append(f"Subject: {subject}")

        context_str = "\n".join(context)

        prompt = f"""Please analyze this legal email and create a concise, professional summary suitable for a billable time entry. Focus on the key legal activities, advice given, or matters discussed.

Email Details:
{context_str}

Content:
{email_content}

Please provide a clear, specific summary that:
1. Describes the main legal activity or service provided
2. Mentions key topics discussed
3. Is written in a professional, billable-entry style
4. Is concise (2-3 sentences maximum)"""

        return prompt

    def _create_billable_description(self, summary, sender_email, recipient_email, subject):
        """Create a formatted billable entry description"""
        if sender_email and recipient_email:
            parties = f"Email correspondence with {recipient_email}"
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


class ClioAuthView(APIView):
    """Handle Clio OAuth2 authentication flow"""

    def get(self, request):
        """Start OAuth flow by redirecting to Clio"""
        auth_url = (
            "https://app.clio.com/oauth/authorize?"
            f"client_id={settings.CLIO_CLIENT_ID}&"
            f"response_type=code&"
            f"redirect_uri={settings.CLIO_REDIRECT_URI}"
        )
        return Response({"auth_url": auth_url})


class ClioCallbackView(APIView):
    """Handle Clio OAuth callback"""

    def get(self, request):
        """Exchange authorization code for access token"""
        code = request.GET.get('code')
        if not code:
            return Response(
                {"error": "No authorization code provided"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # Exchange code for tokens
            response = requests.post(
                "https://app.clio.com/oauth/token",
                data={
                    "client_id": settings.CLIO_CLIENT_ID,
                    "client_secret": settings.CLIO_CLIENT_SECRET,
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": settings.CLIO_REDIRECT_URI
                }
            )

            if response.status_code != 200:
                return Response(
                    {"error": "Failed to get access token"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            token_data = response.json()

            # Get user info from Clio
            user_response = requests.get(
                "https://app.clio.com/api/v4/users/who_am_i",
                headers={
                    "Authorization": f"Bearer {token_data['access_token']}"
                }
            )

            if user_response.status_code != 200:
                return Response(
                    {"error": "Failed to get user info"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            user_data = user_response.json()
            clio_user_id = user_data['data']['id']
            email = user_data['data']['attributes']['email']

            # Save or update user tokens
            ClioUser.objects.update_or_create(
                email=email,
                defaults={
                    'access_token': token_data['access_token'],
                    'refresh_token': token_data['refresh_token'],
                    'token_expires_at': datetime.now() + timedelta(seconds=token_data['expires_in']),
                    'clio_user_id': clio_user_id
                }
            )

            return Response({
                "message": "Authentication successful",
                "email": email
            })

        except Exception as e:
            logger.error(f"Clio authentication error: {str(e)}")
            return Response(
                {"error": "Authentication failed"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class ClioMattersView(APIView):
    """Get list of matters from Clio"""

    def get(self, request):
        """Get matters for authenticated user"""
        user_email = request.GET.get('email')
        if not user_email:
            return Response(
                {"error": "Email parameter required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            clio_service = ClioAPIService(user_email)
            matters = clio_service.get_matters()

            return Response({
                "matters": matters
            })

        except Exception as e:
            logger.error(f"Error fetching matters: {str(e)}")
            return Response(
                {"error": "Failed to fetch matters"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
