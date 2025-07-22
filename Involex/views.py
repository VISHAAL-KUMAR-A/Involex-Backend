from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import api_view, permission_classes
from django.conf import settings
import openai
import time
from .serializers import (
    EmailSummarySerializer, EmailSummaryResponseSerializer,
    PracticePantherUserSerializer, EmailSummaryTimeEntrySerializer,
    OAuthCallbackSerializer, MatterSerializer, TimeEntryCreateSerializer
)
from .services import PracticePantherOAuthService, PracticePantherTimeEntryService
from .models import PracticePantherUser, EmailSummaryTimeEntry

# Add debugging imports
import json
import logging
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token
from datetime import datetime

# Set up logging
logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name='dispatch')  # Add this for CSRF exemption
class EmailSummaryAPIView(APIView):
    """
    API View to summarize emails using OpenAI GPT model.
    Specifically designed for lawyers to create billable entries.
    Now includes automatic PracticePanther time entry creation.
    """
    permission_classes = []  # Remove authentication requirement for now

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
        duration_minutes = validated_data.get(
            'duration_minutes', settings.DEFAULT_TIME_ENTRY_DURATION_MINUTES)
        matter_id = validated_data.get('matter_id')
        create_time_entry = validated_data.get('create_time_entry', True)

        try:
            # Check if this is a test API key
            if settings.OPENAI_API_KEY.startswith('sk-test-key'):
                # Mock response for testing
                summary = f"MOCK: Reviewed email from {sender_email} regarding {subject}. This is a test summary showing that the legal email analysis system is working correctly. Key points identified and next steps recommended."
                logger.info("Using mock OpenAI response for testing")
            else:
                # Initialize OpenAI client
                client = openai.OpenAI(
                    api_key=settings.OPENAI_API_KEY,
                    timeout=30.0
                )

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

            # Prepare base response
            response_data = {
                "summary": summary,
                "word_count_original": original_word_count,
                "word_count_summary": summary_word_count,
                "billable_description": billable_description,
                "processing_time": round(processing_time, 2),
                "time_entry_created": False,
                "time_entry_details": None
            }

            # Try to create PracticePanther time entry if requested and user is authenticated
            if create_time_entry and hasattr(request, 'user') and request.user.is_authenticated:
                try:
                    time_entry_service = PracticePantherTimeEntryService()

                    # Check if user has PracticePanther configuration
                    if hasattr(request.user, 'practice_panther_user') and request.user.practice_panther_user.auto_create_time_entries:
                        email_summary_data = {
                            'summary': summary,
                            'billable_description': billable_description,
                            'subject': subject,
                            'duration_minutes': duration_minutes
                        }

                        # Override matter_id if provided in request
                        if matter_id:
                            email_summary_data['matter_id'] = matter_id

                        time_entry_result = time_entry_service.create_time_entry(
                            request.user, email_summary_data
                        )

                        response_data["time_entry_created"] = time_entry_result.get(
                            'success', False)
                        if time_entry_result.get('success'):
                            response_data["time_entry_details"] = {
                                "time_entry_id": time_entry_result.get('time_entry_id'),
                                "hours": time_entry_result.get('hours'),
                                "rate": time_entry_result.get('rate'),
                                "total": time_entry_result.get('total')
                            }
                        else:
                            logger.warning(
                                f"Failed to create time entry: {time_entry_result.get('error')}")

                except Exception as e:
                    logger.error(f"Error creating time entry: {str(e)}")
                    # Don't fail the entire request if time entry creation fails

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
            "optional_fields": [
                "sender_email", "recipient_email", "subject",
                "duration_minutes", "matter_id", "create_time_entry"
            ],
            "example_request": {
                "email_content": "Dear Client, I have reviewed your contract...",
                "sender_email": "lawyer@lawfirm.com",
                "recipient_email": "client@company.com",
                "subject": "Contract Review Update",
                "duration_minutes": 15,
                "matter_id": "12345",
                "create_time_entry": True
            }
        })


class PracticePantherOAuthInitView(APIView):
    """Initialize PracticePanther OAuth flow"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            oauth_service = PracticePantherOAuthService()
            auth_url = oauth_service.get_authorization_url(
                state=f"user_{request.user.id}"
            )

            return Response({
                "authorization_url": auth_url,
                "message": "Redirect user to this URL to begin OAuth flow"
            })

        except Exception as e:
            return Response(
                {"error": f"Failed to generate authorization URL: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class PracticePantherOAuthCallbackView(APIView):
    """Handle PracticePanther OAuth callback"""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = OAuthCallbackSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"error": "Invalid callback data", "details": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            oauth_service = PracticePantherOAuthService()
            token = oauth_service.exchange_code_for_token(
                serializer.validated_data['code'],
                request.user
            )

            if token:
                return Response({
                    "success": True,
                    "message": "Successfully connected to PracticePanther",
                    "expires_at": token.expires_at.isoformat()
                })
            else:
                return Response(
                    {"error": "Failed to exchange authorization code for token"},
                    status=status.HTTP_400_BAD_REQUEST
                )

        except Exception as e:
            return Response(
                {"error": f"OAuth callback failed: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class PracticePantherUserConfigView(APIView):
    """Manage PracticePanther user configuration"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            pp_user = PracticePantherUser.objects.get(user=request.user)
            serializer = PracticePantherUserSerializer(pp_user)
            return Response(serializer.data)
        except PracticePantherUser.DoesNotExist:
            return Response(
                {"error": "PracticePanther configuration not found"},
                status=status.HTTP_404_NOT_FOUND
            )

    def post(self, request):
        serializer = PracticePantherUserSerializer(data=request.data)
        if serializer.is_valid():
            pp_user, created = PracticePantherUser.objects.update_or_create(
                user=request.user,
                defaults=serializer.validated_data
            )

            response_serializer = PracticePantherUserSerializer(pp_user)
            return Response(
                response_serializer.data,
                status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
            )

        return Response(
            {"error": "Invalid configuration data", "details": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
        )


class PracticePantherMattersView(APIView):
    """Get user's matters from PracticePanther"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            time_entry_service = PracticePantherTimeEntryService()
            matters = time_entry_service.get_user_matters(request.user)

            serializer = MatterSerializer(matters, many=True)
            return Response(serializer.data)

        except Exception as e:
            return Response(
                {"error": f"Failed to fetch matters: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class TimeEntryListView(APIView):
    """List time entries created from email summaries"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        time_entries = EmailSummaryTimeEntry.objects.filter(user=request.user)
        serializer = EmailSummaryTimeEntrySerializer(time_entries, many=True)
        return Response(serializer.data)


class CreateTimeEntryView(APIView):
    """Create a standalone time entry"""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = TimeEntryCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"error": "Invalid time entry data", "details": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            time_entry_service = PracticePantherTimeEntryService()

            validated_data = serializer.validated_data
            email_summary_data = {
                'summary': validated_data['description'],
                'billable_description': validated_data['description'],
                'subject': 'Manual Time Entry',
                'duration_minutes': validated_data['duration_minutes']
            }

            if 'matter_id' in validated_data:
                email_summary_data['matter_id'] = validated_data['matter_id']

            result = time_entry_service.create_time_entry(
                request.user, email_summary_data)

            if result.get('success'):
                return Response({
                    "success": True,
                    "time_entry_id": result.get('time_entry_id'),
                    "details": result
                })
            else:
                return Response(
                    {"error": result.get('error')},
                    status=status.HTTP_400_BAD_REQUEST
                )

        except Exception as e:
            return Response(
                {"error": f"Failed to create time entry: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


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
                    'processing_time': 0.5,
                    'time_entry_created': False,
                    'time_entry_details': None
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


@api_view(['POST'])
@csrf_exempt
def login_view(request):
    """Simple token-based login for Chrome extension"""
    username = request.data.get('username')
    password = request.data.get('password')

    if not username or not password:
        return Response({
            'error': 'Username and password required'
        }, status=status.HTTP_400_BAD_REQUEST)

    user = authenticate(username=username, password=password)
    if user:
        token, created = Token.objects.get_or_create(user=user)

        # Check if user has PracticePanther configuration
        has_pp_config = hasattr(user, 'practice_panther_user')
        has_pp_token = hasattr(user, 'practice_panther_token')

        return Response({
            'token': token.key,
            'user_id': user.id,
            'username': user.username,
            'has_practice_panther_config': has_pp_config,
            'has_practice_panther_token': has_pp_token,
            'message': 'Login successful'
        })

    return Response({
        'error': 'Invalid credentials'
    }, status=status.HTTP_401_UNAUTHORIZED)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def user_status_view(request):
    """Get current user status and PracticePanther configuration"""
    user = request.user

    # Check PracticePanther configuration
    pp_config = None
    if hasattr(user, 'practice_panther_user'):
        pp_config = {
            'practice_panther_user_id': user.practice_panther_user.practice_panther_user_id,
            'default_hourly_rate': float(user.practice_panther_user.default_hourly_rate),
            'auto_create_time_entries': user.practice_panther_user.auto_create_time_entries,
            'default_matter_id': user.practice_panther_user.default_matter_id
        }

    # Check token status
    token_status = None
    if hasattr(user, 'practice_panther_token'):
        token = user.practice_panther_token
        token_status = {
            'has_token': True,
            'expires_at': token.expires_at.isoformat(),
            'is_expired': token.expires_at <= datetime.now()
        }

    return Response({
        'user': {
            'id': user.id,
            'username': user.username,
            'email': user.email
        },
        'practice_panther': {
            'configured': pp_config is not None,
            'config': pp_config,
            'token_status': token_status
        }
    })


@api_view(['POST'])
@csrf_exempt
def register_view(request):
    """Simple user registration for testing"""
    username = request.data.get('username')
    password = request.data.get('password')
    email = request.data.get('email', '')

    if not username or not password:
        return Response({
            'error': 'Username and password required'
        }, status=status.HTTP_400_BAD_REQUEST)

    if User.objects.filter(username=username).exists():
        return Response({
            'error': 'Username already exists'
        }, status=status.HTTP_400_BAD_REQUEST)

    try:
        user = User.objects.create_user(
            username=username, password=password, email=email)
        token, created = Token.objects.get_or_create(user=user)

        return Response({
            'token': token.key,
            'user_id': user.id,
            'username': user.username,
            'message': 'User created successfully'
        }, status=status.HTTP_201_CREATED)

    except Exception as e:
        return Response({
            'error': f'Failed to create user: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
