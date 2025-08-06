from django.shortcuts import render, redirect
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings
import openai
import time
from datetime import datetime, timedelta
from django.utils import timezone
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

    def options(self, request, *args, **kwargs):
        """Handle preflight OPTIONS requests"""
        logger.info("📋 OPTIONS request received for email analysis")
        response = Response(status=status.HTTP_200_OK)
        response["Access-Control-Allow-Origin"] = "*"
        response["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        response["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        return response

    def post(self, request):
        logger.info("📧 EMAIL ANALYSIS POST REQUEST RECEIVED")
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
            clio_entry_error = None

            logger.info(
                f"🔧 DEBUG: Checking Clio entry creation - matter_id: {matter_id}, sender_email: {sender_email}")

            if matter_id and sender_email:
                try:
                    logger.info(
                        f"🔧 DEBUG: Attempting to create Clio billable entry for matter {matter_id}")

                    # Try to get existing user with correct region
                    try:
                        user = ClioUser.objects.get(email=sender_email)
                        logger.info(
                            f"✅ DEBUG: Found ClioUser for email: {sender_email}")
                        # Update region if different
                        if user.region != region:
                            user.region = region
                            user.save()
                            logger.info(
                                f"🔧 DEBUG: Updated user region to: {region}")
                    except ClioUser.DoesNotExist:
                        logger.error(
                            f"❌ ERROR: No ClioUser found for email: {sender_email}")
                        return Response(
                            {"error": "User not authenticated with Clio. Please login first."},
                            status=status.HTTP_401_UNAUTHORIZED
                        )

                    clio_service = ClioAPIService(sender_email)
                    # Assuming 6 minutes (360 seconds) for email communication
                    clio_entry = clio_service.create_time_entry(
                        matter_id=matter_id,
                        date=timezone.now(),
                        duration=360,  # 6 minutes in seconds
                        description=billable_description,
                        # First 500 chars as note
                        note=f"Original email content:\n{email_content[:500]}..."
                    )

                    if clio_entry:
                        logger.info(
                            f"✅ SUCCESS: Clio billable entry created successfully: {clio_entry.get('data', {}).get('id', 'Unknown ID')}")
                    else:
                        logger.warning(
                            f"⚠️ WARNING: Clio entry creation returned None")

                except Exception as e:
                    logger.error(
                        f"❌ ERROR: Failed to create Clio entry: {str(e)}")
                    clio_entry_error = str(e)
                    # Don't fail the whole request if Clio integration fails
                    pass
            else:
                if not matter_id:
                    logger.warning(
                        f"⚠️ WARNING: No matter_id provided - skipping Clio entry creation")
                if not sender_email:
                    logger.warning(
                        f"⚠️ WARNING: No sender_email provided - skipping Clio entry creation")

            processing_time = time.time() - start_time

            # Prepare response
            response_data = {
                "summary": summary,
                "word_count_original": original_word_count,
                "word_count_summary": summary_word_count,
                "billable_description": billable_description,
                "processing_time": round(processing_time, 2),
                "clio_entry_created": bool(clio_entry),
                "clio_entry_id": clio_entry.get('data', {}).get('id') if clio_entry else None,
                "clio_entry_error": clio_entry_error
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
                    'token_expires_at': timezone.now() + timedelta(seconds=token_data['expires_in']),
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
                    'token_expires_at': timezone.now() + timedelta(days=14),  # Set expiry to 14 days
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

            # Transform matter data to include description field for frontend compatibility
            transformed_matters = []
            for matter in matters:
                transformed_matter = {
                    "id": matter.get("id"),
                    "display_number": matter.get("display_number", ""),
                    # Use display_number as description
                    "description": matter.get("display_number", "No description"),
                    "etag": matter.get("etag", "")
                }
                transformed_matters.append(transformed_matter)

            logger.info(f"Transformed matters: {transformed_matters}")

            return Response({
                "matters": transformed_matters
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
            # STEP 1: Just get user data from database (no Clio API calls yet)
            user = ClioUser.objects.get(email=user_email)

            logger.info(
                f"🔧 SIMPLE DEBUG: Found user - ID: {user.clio_user_id}, Email: {user.email}, Region: {user.region}")

            # STEP 2: Now test Clio API with the real user ID
            clio_service = ClioAPIService(user_email)

            # Test 1: Check if user exists in Clio
            try:
                user_info = clio_service._make_request(
                    "GET", f"users/{user.clio_user_id}")
                user_name = user_info.get('data', {}).get('name', 'Unknown')
                logger.info(f"SUCCESS: User exists in Clio: {user_name}")
                user_test_result = {
                    "status": "success", "user_name": user_name}
            except Exception as e:
                logger.error(f"FAILED: User not found in Clio: {str(e)}")
                user_test_result = {"status": "failed", "error": str(e)}

            # Test 2: Check if matter exists and is accessible
            try:
                matter_info = clio_service._make_request(
                    "GET", f"matters/{matter_id}")
                matter_name = matter_info.get('data', {}).get(
                    'display_number', 'Unknown')
                logger.info(f"SUCCESS: Matter exists: {matter_name}")
                matter_test_result = {
                    "status": "success", "matter_name": matter_name}
            except Exception as e:
                logger.error(f"FAILED: Matter not accessible: {str(e)}")
                matter_test_result = {"status": "failed", "error": str(e)}

            # STEP 3a: Test if Activities endpoint exists first
            logger.info("TESTING: Checking if Activities endpoint exists")
            try:
                activities_response = clio_service._make_request(
                    "GET", "activities?limit=1")
                logger.info(
                    "SUCCESS: Activities endpoint exists and is accessible")

                endpoint_test_result = {
                    "status": "success",
                    "message": "Activities endpoint exists",
                    "response_status": "200"
                }
            except Exception as endpoint_error:
                logger.error(
                    f"ERROR: Activities endpoint test failed: {str(endpoint_error)}")
                endpoint_test_result = {
                    "status": "failed",
                    "error": str(endpoint_error),
                    "message": "Activities endpoint does not exist or is not accessible"
                }

            # STEP 3b: Test time entry creation (only if endpoint exists)
            if endpoint_test_result["status"] == "success":
                logger.info("TESTING: Creating billable time entry")
                try:
                    entry = clio_service.create_time_entry(
                        matter_id=matter_id,
                        date=timezone.now(),
                        duration=360,  # 6 minutes
                        description="TEST: Email correspondence analysis via Involex extension",
                        note="This is a test billable entry to verify Clio integration works"
                    )

                    logger.info(
                        f"SUCCESS: Time entry created with ID: {entry.get('data', {}).get('id', 'Unknown')}")

                    time_entry_test_result = {
                        "status": "success",
                        "entry_id": entry.get('data', {}).get('id', 'Unknown'),
                        "entry_description": entry.get('data', {}).get('attributes', {}).get('description', 'Unknown')
                    }
                except Exception as time_entry_error:
                    logger.error(
                        f"ERROR: Time entry creation failed: {str(time_entry_error)}")
                    time_entry_test_result = {
                        "status": "failed",
                        "error": str(time_entry_error)
                    }
            else:
                time_entry_test_result = {
                    "status": "skipped",
                    "reason": "Activities endpoint not accessible"
                }

            # Return the final response
            return Response({
                "message": "User and Matter tests passed, Activities endpoint test completed",
                "database_user_data": {
                    "clio_user_id": user.clio_user_id,
                    "email": user.email,
                    "region": user.region,
                    "selected_matter_id": user.selected_matter_id,
                    "token_expires_at": user.token_expires_at.isoformat() if user.token_expires_at else None,
                    "has_access_token": bool(user.access_token),
                    "has_refresh_token": bool(user.refresh_token)
                },
                "clio_api_tests": {
                    "user_lookup": user_test_result,
                    "matter_lookup": matter_test_result,
                    "activities_endpoint_test": endpoint_test_result,
                    "time_entry_creation": time_entry_test_result
                },
                "requested_matter_id": matter_id,
                "next_step": "Check test results"
            })

        except ClioUser.DoesNotExist:
            return Response(
                {"error": f"No ClioUser found for email: {user_email}"},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error creating test entry: {str(e)}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


@method_decorator(csrf_exempt, name='dispatch')
class UserPreferencesView(APIView):
    """Manage user preferences including selected matter"""

    def get(self, request):
        """Get user preferences"""
        user_email = request.GET.get('email')
        if not user_email:
            return Response(
                {"error": "Email parameter required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            user = ClioUser.objects.get(email=user_email)
            return Response({
                "email": user.email,
                "selected_matter_id": user.selected_matter_id,
                "region": user.region
            })
        except ClioUser.DoesNotExist:
            return Response(
                {"error": "User not found"},
                status=status.HTTP_404_NOT_FOUND
            )

    def post(self, request):
        """Save user preferences"""
        user_email = request.data.get('email')
        selected_matter_id = request.data.get('selected_matter_id')

        if not user_email:
            return Response(
                {"error": "Email is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            user = ClioUser.objects.get(email=user_email)
            if selected_matter_id is not None:
                user.selected_matter_id = selected_matter_id
            user.save()

            logger.info(
                f"Updated preferences for user {user_email}: selected_matter_id={selected_matter_id}")

            return Response({
                "message": "Preferences saved successfully",
                "email": user.email,
                "selected_matter_id": user.selected_matter_id
            })
        except ClioUser.DoesNotExist:
            return Response(
                {"error": "User not authenticated with Clio. Please login first."},
                status=status.HTTP_401_UNAUTHORIZED
            )


@method_decorator(csrf_exempt, name='dispatch')
class TestEmailAnalysisView(APIView):
    """Test endpoint to debug email analysis issues"""

    def options(self, request, *args, **kwargs):
        """Handle preflight OPTIONS requests"""
        logger.info("📋 OPTIONS request received for test email analysis")
        response = Response(status=status.HTTP_200_OK)
        response["Access-Control-Allow-Origin"] = "*"
        response["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        response["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        return response

    def post(self, request):
        """Simple test endpoint to verify POST requests work"""
        logger.info("🧪 TEST EMAIL ANALYSIS POST REQUEST RECEIVED")
        logger.info(f"Request data: {request.data}")

        return Response({
            "status": "success",
            "message": "Test endpoint working",
            "received_data": request.data,
            "timestamp": timezone.now().isoformat()
        })


@method_decorator(csrf_exempt, name='dispatch')
class DebugClioConnectionView(APIView):
    """Debug endpoint to test Clio connection and matter access"""

    def post(self, request):
        """Test Clio connection for a specific user and matter"""
        user_email = request.data.get('email')
        matter_id = request.data.get('matter_id')

        if not user_email:
            return Response(
                {"error": "Email is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # Check if user exists
            user = ClioUser.objects.get(email=user_email)
            logger.info(f"✅ Found user: {user.email}")

            # Test Clio connection
            clio_service = ClioAPIService(user_email)

            # Test basic API access
            try:
                user_info = clio_service._make_request("GET", "users/who_am_i")
                logger.info(
                    f"✅ API connection successful: {user_info.get('data', {}).get('name', 'Unknown')}")
            except Exception as e:
                logger.error(f"❌ API connection failed: {str(e)}")
                return Response({
                    "error": "Clio API connection failed",
                    "details": str(e),
                    "user_found": True,
                    "api_connection": False
                }, status=status.HTTP_400_BAD_REQUEST)

            # Test matter access
            matters_result = {"matters_accessible": False, "matter_ids": []}
            try:
                matters = clio_service.get_matters()
                matter_ids = [m.get('id') for m in matters]
                matters_result = {
                    "matters_accessible": True,
                    "matter_count": len(matters),
                    "matter_ids": matter_ids,
                    "target_matter_exists": matter_id in matter_ids if matter_id else None
                }
                logger.info(f"✅ Found {len(matters)} matters: {matter_ids}")
            except Exception as e:
                logger.error(f"❌ Could not fetch matters: {str(e)}")
                matters_result["error"] = str(e)

            # Test specific matter if provided
            matter_result = {}
            if matter_id:
                try:
                    matter = clio_service._make_request(
                        "GET", f"matters/{matter_id}")
                    matter_result = {
                        "matter_accessible": True,
                        "matter_display_number": matter.get('data', {}).get('display_number', 'Unknown')
                    }
                    logger.info(f"✅ Matter {matter_id} accessible")
                except Exception as e:
                    matter_result = {
                        "matter_accessible": False,
                        "error": str(e)
                    }
                    logger.error(
                        f"❌ Matter {matter_id} not accessible: {str(e)}")

            return Response({
                "user_found": True,
                "api_connection": True,
                "user_email": user.email,
                "token_expires": user.token_expires_at,
                "token_expired": user.token_expires_at <= timezone.now(),
                **matters_result,
                **matter_result
            })

        except ClioUser.DoesNotExist:
            logger.error(f"❌ User not found: {user_email}")
            return Response({
                "error": "User not found in database",
                "user_found": False,
                "available_users": [u.email for u in ClioUser.objects.all()]
            }, status=status.HTTP_404_NOT_FOUND)

        except Exception as e:
            logger.error(f"❌ Debug failed: {str(e)}")
            return Response({
                "error": str(e),
                "user_found": True,
                "debug_failed": True
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class PostmanTimeEntryTestView(APIView):
    """Simple endpoint for Postman API testing - just creates a time entry"""

    def post(self, request):
        """Create a simple time entry for Postman testing"""
        try:
            # Fixed test data - no complex logic
            user_email = "john.wick@clio.user"
            matter_id = "1719986882"

            clio_service = ClioAPIService(user_email)

            # Create time entry with our fixed API call
            entry = clio_service.create_time_entry(
                matter_id=matter_id,
                date=timezone.now(),
                duration=360,  # 6 minutes in seconds
                description="Postman API Test - Time Entry Creation",
                note="Testing time entry creation via API for Involex integration"
            )

            return Response({
                "success": True,
                "message": "Time entry created successfully via API",
                "entry_id": entry.get('data', {}).get('id'),
                "entry_data": entry.get('data', {})
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            return Response({
                "success": False,
                "error": str(e),
                "message": "Time entry creation failed"
            }, status=status.HTTP_400_BAD_REQUEST)


class FetchTimeEntryDetailsView(APIView):
    """Fetch details of a specific time entry by ID"""

    def get(self, request):
        """Get details of the created time entry"""
        try:
            user_email = "john.wick@clio.user"
            entry_id = "7010146637"  # The ID from our most recent successful creation

            clio_service = ClioAPIService(user_email)

            # Fetch the specific time entry details
            entry_details = clio_service._make_request(
                "GET", f"activities/{entry_id}")

            return Response({
                "success": True,
                "message": f"Time entry {entry_id} details retrieved",
                "entry_details": entry_details.get('data', {}),
                "entry_attributes": entry_details.get('data', {}).get('attributes', {}),
                "entry_relationships": entry_details.get('data', {}).get('relationships', {})
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({
                "success": False,
                "error": str(e),
                "message": f"Failed to fetch time entry {entry_id}"
            }, status=status.HTTP_400_BAD_REQUEST)


@method_decorator(csrf_exempt, name='dispatch')
class CreateBillableEntryView(APIView):
    """API endpoint for Chrome extension to create billable entries in Clio"""

    def options(self, request, *args, **kwargs):
        """Handle preflight OPTIONS requests for Chrome extension"""
        logger.info("📋 OPTIONS request received for billable entry creation")
        response = Response(status=status.HTTP_200_OK)
        response["Access-Control-Allow-Origin"] = "*"
        response["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        response["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        return response

    def post(self, request):
        """Create a billable time entry from analyzed email data"""
        logger.info(
            "🔥 CHROME EXTENSION: Billable entry creation request received")
        logger.info(f"Request data: {request.data}")

        # Extract required parameters
        user_email = request.data.get('user_email')
        analyzed_email_description = request.data.get(
            'email_description')  # Analyzed email summary
        # Can be provided or use user preference
        matter_id = request.data.get('matter_id')
        # Default rate if not provided
        billable_rate = request.data.get('rate', 150.0)
        duration_minutes = request.data.get(
            'duration_minutes', 6)  # Default 6 minutes
        email_subject = request.data.get('email_subject', '')
        sender_email = request.data.get('sender_email', '')
        recipient_email = request.data.get('recipient_email', '')

        # Validate required fields
        if not user_email:
            return Response({
                "error": "user_email is required",
                "status": "error"
            }, status=status.HTTP_400_BAD_REQUEST)

        if not analyzed_email_description:
            return Response({
                "error": "email_description is required",
                "status": "error"
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Check if user exists and is authenticated
            try:
                user = ClioUser.objects.get(email=user_email)
                logger.info(f"✅ Found authenticated user: {user_email}")
            except ClioUser.DoesNotExist:
                logger.error(f"❌ User not authenticated: {user_email}")
                return Response({
                    "error": "User not authenticated with Clio. Please login first.",
                    "status": "error",
                    "auth_required": True
                }, status=status.HTTP_401_UNAUTHORIZED)

            # If no matter_id provided, use user's selected matter from preferences
            if not matter_id:
                if user.selected_matter_id:
                    matter_id = user.selected_matter_id
                    logger.info(
                        f"🔧 Using user's preferred matter: {matter_id}")
                else:
                    return Response({
                        "error": "No matter specified and user has no default matter set",
                        "status": "error",
                        "need_matter_selection": True
                    }, status=status.HTTP_400_BAD_REQUEST)

            # Create professional billable description
            if sender_email and recipient_email:
                parties = f"Email correspondence with {recipient_email}"
            elif sender_email:
                parties = f"Email correspondence from {sender_email}"
            else:
                parties = "Email correspondence"

            subject_text = f" regarding {email_subject}" if email_subject else ""
            billable_description = f"{parties}{subject_text}. {analyzed_email_description}"

            # Create Clio time entry
            clio_service = ClioAPIService(user_email)

            # Convert minutes to seconds for Clio API
            duration_seconds = duration_minutes * 60

            logger.info(f"🔧 Creating billable entry:")
            logger.info(f"   Matter ID: {matter_id}")
            logger.info(
                f"   Duration: {duration_minutes} minutes ({duration_seconds} seconds)")
            logger.info(f"   Rate: ${billable_rate}/hr")
            logger.info(f"   Description: {billable_description[:100]}...")

            clio_entry = clio_service.create_time_entry(
                matter_id=matter_id,
                date=timezone.now(),
                duration=duration_seconds,
                description=billable_description,
                note=f"Created via Involex Chrome Extension. Rate: ${billable_rate}/hr"
            )

            if clio_entry:
                entry_id = clio_entry.get('data', {}).get('id')
                logger.info(
                    f"✅ SUCCESS: Billable entry created with ID: {entry_id}")

                return Response({
                    "status": "success",
                    "message": "Billable entry created successfully",
                    "entry_id": entry_id,
                    "matter_id": matter_id,
                    "duration_minutes": duration_minutes,
                    "rate": billable_rate,
                    "description": billable_description,
                    "clio_entry_data": clio_entry.get('data', {})
                }, status=status.HTTP_201_CREATED)
            else:
                logger.error("❌ Clio entry creation returned None")
                return Response({
                    "error": "Failed to create billable entry - unknown error",
                    "status": "error"
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        except Exception as e:
            logger.error(f"❌ ERROR creating billable entry: {str(e)}")
            return Response({
                "error": str(e),
                "status": "error"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def get(self, request):
        """GET method to provide API documentation for Chrome extension"""
        return Response({
            "message": "Chrome Extension Billable Entry API",
            "description": "POST analyzed email data to create billable time entries in Clio",
            "endpoint": "/api/clio/create-billable/",
            "method": "POST",
            "required_fields": ["user_email", "email_description"],
            "optional_fields": [
                "matter_id (uses user preference if not provided)",
                "rate (default: 150.0)",
                "duration_minutes (default: 6)",
                "email_subject",
                "sender_email",
                "recipient_email"
            ],
            "example_request": {
                "user_email": "john.wick@clio.user",
                "email_description": "Discussed contract terms and negotiation strategy with client",
                "matter_id": "1719986882",
                "rate": 250.0,
                "duration_minutes": 10,
                "email_subject": "Contract Review",
                "sender_email": "client@company.com",
                "recipient_email": "lawyer@lawfirm.com"
            },
            "response_example": {
                "status": "success",
                "message": "Billable entry created successfully",
                "entry_id": 7012644961,
                "matter_id": "1719986882",
                "duration_minutes": 10,
                "rate": 250.0
            }
        })
