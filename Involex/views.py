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
        logger.info("OPTIONS request received for email analysis")
        response = Response(status=status.HTTP_200_OK)
        response["Access-Control-Allow-Origin"] = "*"
        response["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        response["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        return response

    def post(self, request):
        logger.info("EMAIL ANALYSIS POST REQUEST RECEIVED")
        logger.info(f"DEBUG: Request headers: {dict(request.headers)}")
        logger.info(f"DEBUG: Request body: {request.body[:500]}...")

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

            # Store AI analysis in cache for later retrieval by latest-ai-analysis API
            # NO BILLABLE ENTRY CREATION HERE - Only analysis and caching
            logger.info(
                "STORING AI ANALYSIS IN CACHE - No billable entry creation")

            try:
                from django.core.cache import cache
                cache_key = f"latest_ai_analysis_{sender_email}"
                cache.set(cache_key, {
                    'ai_summary': summary,
                    'billable_description': billable_description,
                    'sender_email': sender_email,
                    'recipient_email': recipient_email,
                    'email_subject': subject,
                    # Store first 500 chars
                    'email_content': email_content[:500],
                    'analyzed_at': timezone.now().isoformat(),
                    'word_count_original': original_word_count,
                    'word_count_summary': summary_word_count
                }, timeout=3600)  # Store for 1 hour

                logger.info(
                    f"SUCCESS: AI analysis cached for user: {sender_email}")
                logger.info(f"CACHE KEY: {cache_key}")
                logger.info(f"AI SUMMARY: {summary[:100]}...")
            except Exception as cache_error:
                logger.error(
                    f"ERROR: Failed to cache AI analysis: {cache_error}")

            processing_time = time.time() - start_time

            # Prepare response - NO CLIO ENTRY CREATION
            response_data = {
                "summary": summary,
                "word_count_original": original_word_count,
                "word_count_summary": summary_word_count,
                "billable_description": billable_description,
                "processing_time": round(processing_time, 2),
                "clio_entry_created": False,  # No billable entry created
                "clio_entry_id": None,
                "clio_entry_error": None
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
    logger.info(f"DEBUG: Request method: {request.method}")
    logger.info(f"DEBUG: Request headers: {dict(request.headers)}")
    logger.info(f"DEBUG: Request content type: {request.content_type}")
    logger.info(f"DEBUG: Request body (raw): {request.body}")

    if request.method == 'POST':
        try:
            # Try to parse JSON
            if request.content_type == 'application/json':
                data = json.loads(request.body)
                logger.info(f"DEBUG: Parsed JSON data: {data}")

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

                logger.info(f"DEBUG: All required fields present")
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
                        note="This is a test billable entry to verify Clio integration works",
                        hourly_rate=200.0  # Test rate
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
        logger.info("OPTIONS request received for test email analysis")
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
            logger.info(f"SUCCESS: Found user: {user.email}")

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
                logger.info(
                    f"SUCCESS: Found {len(matters)} matters: {matter_ids}")
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
                    logger.info(f"SUCCESS: Matter {matter_id} accessible")
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
                note="Testing time entry creation via API for Involex integration",
                hourly_rate=225.0  # Test rate for Postman
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
        logger.info("OPTIONS request received for billable entry creation")
        response = Response(status=status.HTTP_200_OK)
        response["Access-Control-Allow-Origin"] = "*"
        response["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        response["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        return response

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

    def post(self, request):
        """Create a billable time entry from analyzed email data or analyze content first"""
        logger.info(
            "CHROME EXTENSION: Billable entry creation request received")
        logger.info(f"Request data: {request.data}")

        # Extract required parameters
        user_email = request.data.get('user_email')
        # Could be raw content or analyzed summary
        email_description = request.data.get('email_description')
        matter_id = request.data.get('matter_id')
        billable_rate = request.data.get('rate', 150.0)
        duration_minutes = request.data.get('duration_minutes', 6)
        email_subject = request.data.get('email_subject', '')
        sender_email = request.data.get('sender_email', '')
        recipient_email = request.data.get('recipient_email', '')

        # NEW: Accept pre-analyzed billable_description from latest-ai-analysis API
        provided_billable_description = request.data.get(
            'billable_description')

        # NEW: Flag to indicate if we should analyze the content with OpenAI first
        analyze_content = request.data.get('analyze_content', False)

        # PREVENT DUPLICATES: Check if this exact request was recently processed
        from django.core.cache import cache
        # Use email_description or billable_description for hash (whichever is provided)
        description_for_hash = email_description or provided_billable_description or ""
        request_hash = f"{user_email}_{description_for_hash[:50]}_{email_subject}_{analyze_content}"
        duplicate_key = f"billable_request_{hash(request_hash)}"

        if cache.get(duplicate_key):
            logger.warning(f"DUPLICATE REQUEST BLOCKED: {request_hash[:100]}")
            return Response({
                "error": "Duplicate request detected. Please wait before sending another email.",
                "status": "error"
            }, status=status.HTTP_409_CONFLICT)

        # Mark this request as processed for 30 seconds
        cache.set(duplicate_key, True, timeout=30)

        # Validate required fields
        if not user_email:
            return Response({
                "error": "user_email is required",
                "status": "error"
            }, status=status.HTTP_400_BAD_REQUEST)

        # Require either email_description OR billable_description (from AI analysis)
        if not email_description and not provided_billable_description:
            return Response({
                "error": "Either email_description or billable_description is required",
                "status": "error"
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Check if user exists and is authenticated
            try:
                user = ClioUser.objects.get(email=user_email)
                logger.info(f"SUCCESS: Found authenticated user: {user_email}")
            except ClioUser.DoesNotExist:
                logger.error(f"ERROR: User not authenticated: {user_email}")
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

            # Check if billable_description is provided (from latest-ai-analysis API)
            if provided_billable_description:
                # Use the pre-analyzed description from frontend (via latest-ai-analysis API)
                logger.info(
                    "USING PRE-ANALYZED DESCRIPTION from latest-ai-analysis API")
                billable_description = provided_billable_description
                logger.info(
                    f"PRE-ANALYZED DESCRIPTION: {billable_description[:100]}...")
            elif analyze_content:
                logger.info(
                    "STARTING AI ANALYSIS - This may take 10-15 seconds...")
                try:
                    # Initialize OpenAI client
                    client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)

                    # Add timeout and retry logic for OpenAI API
                    import time
                    start_time = time.time()

                    # Create the prompt for legal email summarization
                    prompt = self._create_legal_summary_prompt(
                        email_description, sender_email, recipient_email, email_subject
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

                    ai_summary = response.choices[0].message.content.strip()
                    analysis_time = time.time() - start_time

                    logger.info(
                        f"SUCCESS: OpenAI analysis completed in {analysis_time:.2f} seconds")
                    logger.info(f"FULL AI SUMMARY: {ai_summary}")

                    # Ensure AI summary is not empty
                    if not ai_summary or len(ai_summary.strip()) < 10:
                        raise Exception(
                            "AI analysis returned empty or too short summary")

                    # Store AI analysis in database for the new API endpoint
                    from django.core.cache import cache
                    cache_key = f"latest_ai_analysis_{user_email}"
                    cache.set(cache_key, {
                        'ai_summary': ai_summary,
                        'sender_email': sender_email,
                        'recipient_email': recipient_email,
                        'email_subject': email_subject,
                        'analyzed_at': timezone.now().isoformat(),
                        'billable_description': None  # Will be set below
                    }, timeout=3600)  # Store for 1 hour

                    # Create professional billable description using AI analysis
                    billable_description = self._create_billable_description(
                        ai_summary, sender_email, recipient_email, email_subject
                    )

                    # Validate billable description was created correctly
                    if not billable_description or "Email correspondence" not in billable_description:
                        logger.error(
                            f"ERROR: Billable description creation failed!")
                        logger.error(f"   AI Summary: {ai_summary}")
                        logger.error(
                            f"   Billable Description: {billable_description}")
                        raise Exception(
                            "Failed to create proper billable description from AI analysis")

                    # Update cache with billable description
                    cached_data = cache.get(cache_key)
                    if cached_data:
                        cached_data['billable_description'] = billable_description
                        cache.set(cache_key, cached_data, timeout=3600)

                    logger.info(
                        f"AI ANALYSIS COMPLETE - SUMMARY: {ai_summary[:100]}...")
                    logger.info(
                        f"AI ANALYSIS COMPLETE - BILLABLE DESC: {billable_description[:100]}...")
                    logger.info(
                        f"NOW PROCEEDING TO CREATE CLIO ENTRY WITH AI ANALYSIS")

                except Exception as e:
                    logger.error(f"ERROR: OpenAI analysis failed: {str(e)}")
                    return Response({
                        "error": f"Failed to analyze email content: {str(e)}",
                        "status": "error"
                    }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            else:
                # Use the provided description as-is (raw content - no analysis)
                logger.info(
                    "Using provided email description as raw content (no analysis)")
                if sender_email and recipient_email:
                    parties = f"Email correspondence with {recipient_email}"
                elif sender_email:
                    parties = f"Email correspondence from {sender_email}"
                else:
                    parties = "Email correspondence"

                subject_text = f" regarding {email_subject}" if email_subject else ""
                billable_description = f"{parties}{subject_text}. {email_description}"

            # Create Clio time entry
            clio_service = ClioAPIService(user_email)

            # Convert minutes to seconds for Clio API
            duration_seconds = duration_minutes * 60

            logger.info(f"DEBUG: Creating billable entry:")
            logger.info(f"   Matter ID: {matter_id}")
            logger.info(
                f"   Duration: {duration_minutes} minutes ({duration_seconds} seconds)")
            logger.info(f"   Rate: ${billable_rate}/hr")
            logger.info(f"   Description (FULL): {billable_description}")

            # FIXED: Put AI analysis in BOTH description and note fields since Clio displays note prominently
            if provided_billable_description or analyze_content:
                # For AI-analyzed content, put the analysis in BOTH fields
                # AI analysis goes in note (what Clio displays)
                note_content = billable_description
                logger.info(
                    f"   AI ANALYSIS IN BOTH DESCRIPTION AND NOTE: {billable_description[:100]}...")
            else:
                # For raw content, use simple note
                note_content = f"Email entry created via Involex extension. Rate: ${billable_rate}/hr"

            logger.info(f"   Note (FULL): {note_content}")

            logger.info(f"FINAL DEBUG - SENDING TO CLIO:")
            logger.info(
                f"   description parameter: '{billable_description[:100]}...'")
            logger.info(f"   note parameter: '{note_content[:100]}...'")
            logger.info(
                f"   Both fields contain AI analysis: {provided_billable_description or analyze_content}")

            clio_entry = clio_service.create_time_entry(
                matter_id=matter_id,
                date=timezone.now(),
                duration=duration_seconds,
                description=billable_description,
                note=note_content,
                hourly_rate=billable_rate
            )

            if clio_entry:
                entry_id = clio_entry.get('data', {}).get('id')
                logger.info(
                    f"SUCCESS: Billable entry created with ID: {entry_id}")

                return Response({
                    "status": "success",
                    "message": "Billable entry created successfully with AI analysis" if analyze_content else "Billable entry created successfully",
                    "entry_id": entry_id,
                    "matter_id": matter_id,
                    "duration_minutes": duration_minutes,
                    "rate": billable_rate,
                    "description": billable_description,
                    "analyzed_content": analyze_content,
                    "ai_analysis_in_description": analyze_content,
                    "clio_entry_data": clio_entry.get('data', {})
                }, status=status.HTTP_201_CREATED)
            else:
                logger.error("ERROR: Clio entry creation returned None")
                return Response({
                    "error": "Failed to create billable entry - unknown error",
                    "status": "error"
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        except Exception as e:
            logger.error(f"ERROR creating billable entry: {str(e)}")
            return Response({
                "error": str(e),
                "status": "error"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def get(self, request):
        """GET method to provide API documentation for Chrome extension"""
        return Response({
            "message": "Chrome Extension Billable Entry API",
            "description": "POST email data to create billable time entries in Clio. Can analyze raw email content with AI or use pre-analyzed descriptions.",
            "endpoint": "/api/clio/create-billable/",
            "method": "POST",
            "required_fields": ["user_email", "email_description"],
            "optional_fields": [
                "matter_id (uses user preference if not provided)",
                "rate (default: 150.0)",
                "duration_minutes (default: 6)",
                "email_subject",
                "sender_email",
                "recipient_email",
                "analyze_content (default: false) - Set to true to analyze raw email content with OpenAI"
            ],
            "example_request_with_analysis": {
                "user_email": "john.wick@clio.user",
                "email_description": "Hi John, Can you please review the attached contract and let me know your thoughts on the liability clauses? We need to finalize this by Friday. Thanks, Client",
                "matter_id": "1719986882",
                "rate": 325.0,
                "duration_minutes": 12,
                "email_subject": "Contract Review",
                "sender_email": "client@company.com",
                "recipient_email": "lawyer@lawfirm.com",
                "analyze_content": True
            },
            "example_request_pre_analyzed": {
                "user_email": "john.wick@clio.user",
                "email_description": "Contract analysis and legal advice provided regarding liability clauses",
                "matter_id": "1719986882",
                "rate": 250.0,
                "duration_minutes": 10,
                "email_subject": "Contract Review",
                "sender_email": "client@company.com",
                "recipient_email": "lawyer@lawfirm.com",
                "analyze_content": False
            },
            "response_example": {
                "status": "success",
                "message": "Billable entry created successfully",
                "entry_id": 7012644961,
                "matter_id": "1719986882",
                "duration_minutes": 10,
                "rate": 250.0,
                "analyzed_content": True,
                "description": "Email correspondence with client@company.com regarding Contract Review. Contract analysis and legal advice provided regarding liability clauses with emphasis on risk mitigation strategies."
            }
        })


@method_decorator(csrf_exempt, name='dispatch')
class LatestAIAnalysisView(APIView):
    """API endpoint to get the latest AI email analysis for a user"""

    def options(self, request, *args, **kwargs):
        """Handle preflight OPTIONS requests"""
        logger.info("OPTIONS request received for latest AI analysis")
        response = Response(status=status.HTTP_200_OK)
        response["Access-Control-Allow-Origin"] = "*"
        response["Access-Control-Allow-Methods"] = "GET, OPTIONS"
        response["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        return response

    def get(self, request):
        """Get the latest AI analysis for a user"""
        user_email = request.GET.get('user_email')

        if not user_email:
            return Response({
                "error": "user_email parameter required",
                "status": "error"
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Get latest AI analysis from cache
            from django.core.cache import cache
            cache_key = f"latest_ai_analysis_{user_email}"
            cached_data = cache.get(cache_key)

            if not cached_data:
                return Response({
                    "error": "No recent AI analysis found for this user",
                    "status": "error",
                    "message": "Please send an email first to generate AI analysis"
                }, status=status.HTTP_404_NOT_FOUND)

            return Response({
                "status": "success",
                "data": {
                    "ai_summary": cached_data['ai_summary'],
                    "billable_description": cached_data['billable_description'],
                    "sender_email": cached_data['sender_email'],
                    "recipient_email": cached_data['recipient_email'],
                    "email_subject": cached_data['email_subject'],
                    "analyzed_at": cached_data['analyzed_at']
                }
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error retrieving latest AI analysis: {str(e)}")
            return Response({
                "error": str(e),
                "status": "error"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
