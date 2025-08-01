from django.shortcuts import render, redirect
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings
import openai
import time
from datetime import datetime, timedelta
from .serializers import EmailSummarySerializer, EmailSummaryResponseSerializer
from .services import ClioAPIService
from .models import ClioUser
import requests
import json
import logging
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.middleware.csrf import get_token

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
        matter_id = validated_data.get('matter_id')
        # Get region from request
        region = validated_data.get('region', 'NA').upper()

        if region not in ['NA', 'EU', 'CA']:
            region = 'NA'

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
                    # Try to get existing user with correct region
                    try:
                        user = ClioUser.objects.get(email=sender_email)
                        # Update region if different
                        if user.region != region:
                            user.region = region
                            user.save()
                    except ClioUser.DoesNotExist:
                        logger.error(
                            f"No ClioUser found for email: {sender_email}")
                        return Response(
                            {"error": "User not authenticated with Clio. Please login first."},
                            status=status.HTTP_401_UNAUTHORIZED
                        )

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


@method_decorator(csrf_exempt, name='dispatch')
class ClioAuthView(APIView):
    """Handle Clio OAuth2 authentication flow"""

    def get(self, request):
        """Start OAuth flow by redirecting to Clio"""
        logger.info("Starting Clio OAuth flow")

        # Always use NA region for India
        base_url = 'https://app.clio.com'

        logger.info(f"Using base URL: {base_url}")
        logger.info(f"Using client_id: {settings.CLIO_CLIENT_ID[:5]}...")
        logger.info(f"Redirect URI: {settings.CLIO_REDIRECT_URI}")

        auth_url = (
            f"{base_url}/oauth/authorize?"
            f"client_id={settings.CLIO_CLIENT_ID}&"
            f"response_type=code&"
            f"redirect_uri={settings.CLIO_REDIRECT_URI}"
        )

        logger.info(
            f"Generated auth URL (client_id hidden): {auth_url.replace(settings.CLIO_CLIENT_ID, 'CLIENT_ID')}")

        # Add manual test instruction
        logger.info(f"MANUAL TEST: Copy this URL and test in browser:")
        logger.info(f"Auth URL: {auth_url}")

        return Response({
            "auth_url": auth_url
        }, headers={
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type, Authorization'
        })


@method_decorator(csrf_exempt, name='dispatch')
class ClioCallbackView(APIView):
    """Handle Clio OAuth callback"""

    def options(self, request, *args, **kwargs):
        """Handle CORS preflight requests for callback"""
        logger.info("OPTIONS request received on callback endpoint")
        response = JsonResponse({'status': 'ok'})
        response['Access-Control-Allow-Origin'] = '*'
        response['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
        response['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        return response

    def get(self, request):
        """Exchange authorization code for access token"""
        # Add extensive debugging
        logger.info(f"=== CLIO CALLBACK RECEIVED ===")
        logger.info(f"SUCCESS: Callback URL was hit!")
        logger.info(f"Full request URL: {request.build_absolute_uri()}")
        logger.info(f"Query parameters: {dict(request.GET)}")
        logger.info(f"Headers: {dict(request.headers)}")
        logger.info(f"Request method: {request.method}")
        logger.info(f"Request path: {request.path}")

        code = request.GET.get('code')
        error = request.GET.get('error')
        error_description = request.GET.get('error_description')

        base_url = 'https://app.clio.com'  # Always use NA region

        logger.info(
            f"Received OAuth callback with code: {code[:5] if code else 'None'}...")

        # Check for OAuth errors first
        if error:
            logger.error(f"OAuth error received: {error}")
            logger.error(f"OAuth error description: {error_description}")
            response = JsonResponse({
                "status": "error",
                "error": error,
                "error_description": error_description or "OAuth authentication failed"
            }, status=400)
            response['Access-Control-Allow-Origin'] = '*'
            return response

        if not code:
            logger.error("No authorization code provided in callback")
            response = JsonResponse({
                "status": "error",
                "error": "no_code",
                "error_description": "No authorization code provided"
            }, status=400)
            response['Access-Control-Allow-Origin'] = '*'
            return response

        try:
            # Exchange code for tokens
            logger.info("Exchanging code for tokens...")
            token_response = requests.post(
                f"{base_url}/oauth/token",
                data={
                    "client_id": settings.CLIO_CLIENT_ID,
                    "client_secret": settings.CLIO_CLIENT_SECRET,
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": settings.CLIO_REDIRECT_URI
                }
            )

            logger.info(
                f"Token exchange response status: {token_response.status_code}")
            logger.info(f"Token exchange response: {token_response.text}")

            if token_response.status_code != 200:
                error_msg = token_response.text
                logger.error(f"Token exchange failed: {error_msg}")
                response = JsonResponse({
                    "status": "error",
                    "error": f"Failed to get access token: {error_msg}"
                }, status=400)
                response['Access-Control-Allow-Origin'] = '*'
                return response

            token_data = token_response.json()
            logger.info("Successfully got token data")

            # Get user info from Clio
            logger.info("Fetching user info from Clio...")
            user_response = requests.get(
                f"{base_url}/api/v4/users/who_am_i",
                headers={
                    "Authorization": f"Bearer {token_data['access_token']}"
                }
            )

            logger.info(
                f"User info response status: {user_response.status_code}")
            if user_response.status_code != 200:
                error_msg = user_response.text
                logger.error(f"Failed to get user info: {error_msg}")
                response = JsonResponse({
                    "status": "error",
                    "error": f"Failed to get user info: {error_msg}"
                }, status=400)
                response['Access-Control-Allow-Origin'] = '*'
                return response

            user_data = user_response.json()
            logger.info(f"User data response: {json.dumps(user_data)}")

            try:
                # Get user info from the who_am_i response
                if not user_data.get('data', {}).get('id'):
                    raise ValueError("Could not find user ID in response")

                clio_user_id = user_data['data']['id']
                user_name = user_data['data'].get('name', '')

                if not user_name:
                    raise ValueError("Could not find user name in response")

                # Use name@clio.user as a unique identifier
                email = f"{user_name.lower().replace(' ', '.')}@clio.user"

                logger.info(
                    f"Got user info - ID: {clio_user_id}, Name: {user_name}, Generated Email: {email}")

            except (KeyError, ValueError) as e:
                logger.error(f"Error parsing user data: {str(e)}")
                response = JsonResponse({
                    "status": "error",
                    "error": f"Failed to parse user data: {str(e)}"
                }, status=500)
                response['Access-Control-Allow-Origin'] = '*'
                return response

            # Save or update user tokens
            user, created = ClioUser.objects.update_or_create(
                email=email,
                defaults={
                    'access_token': token_data['access_token'],
                    'refresh_token': token_data['refresh_token'],
                    'token_expires_at': datetime.now() + timedelta(seconds=token_data['expires_in']),
                    'clio_user_id': clio_user_id
                }
            )

            action = 'Created new' if created else 'Updated existing'
            logger.info(f"{action} ClioUser record for {email}")

            # Return JSON response instead of redirect
            response = JsonResponse({
                "message": "Authentication successful",
                "email": email,
                "status": "success"
            })
            response['Access-Control-Allow-Origin'] = '*'
            return response

        except Exception as e:
            logger.error(f"Clio authentication error: {str(e)}")
            response = JsonResponse({
                "error": str(e),
                "status": "error"
            }, status=500)
            response['Access-Control-Allow-Origin'] = '*'
            return response

# Add test endpoint to manually create/update Clio user


class ClioConfigTestView(APIView):
    """Test endpoint to verify Clio configuration"""

    def get(self, request):
        """Check if Clio environment variables are properly configured"""
        config_status = {
            "clio_client_id": bool(settings.CLIO_CLIENT_ID),
            "clio_client_secret": bool(settings.CLIO_CLIENT_SECRET),
            "clio_redirect_uri": settings.CLIO_REDIRECT_URI,
            "client_id_length": len(settings.CLIO_CLIENT_ID) if settings.CLIO_CLIENT_ID else 0,
            "client_id_preview": settings.CLIO_CLIENT_ID[:5] + "..." if settings.CLIO_CLIENT_ID else "Not set",
            "auth_url_test": f"https://app.clio.com/oauth/authorize?client_id={settings.CLIO_CLIENT_ID[:5]}...&response_type=code&redirect_uri={settings.CLIO_REDIRECT_URI}" if settings.CLIO_CLIENT_ID else "Cannot generate - missing client ID"
        }

        response = JsonResponse(config_status)
        response['Access-Control-Allow-Origin'] = '*'
        return response


class TestClioUserView(APIView):
    """Test endpoint to manually create/update Clio user"""

    def post(self, request):
        """Create or update a Clio user manually"""
        email = request.data.get('email')
        access_token = request.data.get('access_token')
        refresh_token = request.data.get('refresh_token')
        region = request.data.get('region', 'NA').upper()

        if not all([email, access_token, refresh_token]):
            return Response(
                {"error": "email, access_token, and refresh_token are required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if region not in ['NA', 'EU', 'CA']:
            region = 'NA'

        try:
            # Create or update user
            user, created = ClioUser.objects.update_or_create(
                email=email,
                defaults={
                    'access_token': access_token,
                    'refresh_token': refresh_token,
                    'token_expires_at': datetime.now() + timedelta(days=14),  # Set expiry to 14 days
                    'clio_user_id': 'manual_test',  # Placeholder ID for manual creation
                    'region': region
                }
            )

            action = 'Created' if created else 'Updated'
            return Response({
                "message": f"{action} Clio user successfully",
                "email": email,
                "region": region
            })

        except Exception as e:
            logger.error(f"Error creating test Clio user: {str(e)}")
            return Response(
                {"error": str(e)},
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
            # Add debug logging
            logger.info(f"Fetching matters for email: {user_email}")

            # Check if user exists in database
            try:
                user = ClioUser.objects.get(email=user_email)
                logger.info(f"Found user in database: {user.email}")
                logger.info(f"Access token exists: {bool(user.access_token)}")
                logger.info(f"Token expires at: {user.token_expires_at}")
            except ClioUser.DoesNotExist:
                logger.error(f"No ClioUser found for email: {user_email}")
                return Response(
                    {"error": "User not authenticated with Clio. Please login first."},
                    status=status.HTTP_401_UNAUTHORIZED
                )

            clio_service = ClioAPIService(user_email)
            matters = clio_service.get_matters()

            return Response({
                "matters": matters
            })

        except Exception as e:
            logger.error(f"Error fetching matters: {str(e)}")
            # Return more detailed error message
            return Response(
                {"error": f"Failed to fetch matters: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


@method_decorator(csrf_exempt, name='dispatch')
class ClioLogoutView(APIView):
    """Handle Clio logout"""

    def post(self, request):
        """Clear Clio tokens for a user"""
        email = request.data.get('email')

        if not email:
            return Response(
                {"error": "Email is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            user = ClioUser.objects.get(email=email)
            user.delete()
            return Response({
                "message": "Successfully logged out",
                "email": email
            })
        except ClioUser.DoesNotExist:
            return Response({
                "message": "User was not logged in",
                "email": email
            })


class TestClioEntryView(APIView):
    """Test endpoint to create a Clio billable entry"""

    def post(self, request):
        """Create a test billable entry"""
        user_email = request.data.get('email')
        matter_id = request.data.get('matter_id')

        if not user_email or not matter_id:
            return Response(
                {"error": "Both email and matter_id are required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            clio_service = ClioAPIService(user_email)

            # Create a test time entry
            entry = clio_service.create_time_entry(
                matter_id=matter_id,
                date=datetime.now(),
                duration=360,  # 6 minutes
                description="Test billable entry from Involex",
                note="This is a test entry to verify Clio integration"
            )

            return Response({
                "message": "Test entry created successfully",
                "entry": entry
            })

        except Exception as e:
            logger.error(f"Error creating test entry: {str(e)}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
