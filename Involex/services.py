import requests
import logging
from datetime import datetime, timedelta
from django.conf import settings
from django.contrib.auth.models import User
from .models import PracticePantherToken, PracticePantherUser, EmailSummaryTimeEntry
from urllib.parse import urlencode

logger = logging.getLogger(__name__)


class PracticePantherOAuthService:
    """Service to handle PracticePanther OAuth 2.0 authentication"""

    def __init__(self):
        self.base_url = settings.PRACTICE_PANTHER_BASE_URL
        self.client_id = settings.PRACTICE_PANTHER_CLIENT_ID
        self.client_secret = settings.PRACTICE_PANTHER_CLIENT_SECRET
        self.redirect_uri = settings.PRACTICE_PANTHER_REDIRECT_URI

    def get_authorization_url(self, state=None):
        """Generate the authorization URL for OAuth flow"""
        if not self.client_id or not self.redirect_uri:
            raise ValueError(
                "PracticePanther OAuth credentials not configured")

        params = {
            'response_type': 'code',
            'client_id': self.client_id,
            'redirect_uri': self.redirect_uri,
            'state': state or 'default_state'
        }

        return f"{self.base_url}/oauth/authorize?{urlencode(params)}"

    def exchange_code_for_token(self, authorization_code, user):
        """Exchange authorization code for access token"""
        try:
            data = {
                'grant_type': 'authorization_code',
                'code': authorization_code,
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'redirect_uri': self.redirect_uri
            }

            response = requests.post(
                f"{self.base_url}/oauth/token",
                data=data,
                headers={'Content-Type': 'application/x-www-form-urlencoded'}
            )

            if response.status_code == 200:
                token_data = response.json()

                # Calculate expiration time
                expires_in = token_data.get(
                    'expires_in', 3600)  # Default 1 hour
                expires_at = datetime.now() + timedelta(seconds=expires_in)

                # Save or update token
                token, created = PracticePantherToken.objects.update_or_create(
                    user=user,
                    defaults={
                        'access_token': token_data['access_token'],
                        'refresh_token': token_data.get('refresh_token', ''),
                        'expires_at': expires_at
                    }
                )

                logger.info(
                    f"Successfully {'created' if created else 'updated'} token for user {user.username}")
                return token
            else:
                logger.error(
                    f"Token exchange failed: {response.status_code} - {response.text}")
                return None

        except Exception as e:
            logger.error(f"Error during token exchange: {str(e)}")
            return None

    def refresh_token(self, user):
        """Refresh an expired access token"""
        try:
            token = PracticePantherToken.objects.get(user=user)

            data = {
                'grant_type': 'refresh_token',
                'refresh_token': token.refresh_token,
                'client_id': self.client_id,
                'client_secret': self.client_secret
            }

            response = requests.post(
                f"{self.base_url}/oauth/token",
                data=data,
                headers={'Content-Type': 'application/x-www-form-urlencoded'}
            )

            if response.status_code == 200:
                token_data = response.json()

                expires_in = token_data.get('expires_in', 3600)
                expires_at = datetime.now() + timedelta(seconds=expires_in)

                token.access_token = token_data['access_token']
                if 'refresh_token' in token_data:
                    token.refresh_token = token_data['refresh_token']
                token.expires_at = expires_at
                token.save()

                logger.info(
                    f"Successfully refreshed token for user {user.username}")
                return token
            else:
                logger.error(
                    f"Token refresh failed: {response.status_code} - {response.text}")
                return None

        except Exception as e:
            logger.error(f"Error during token refresh: {str(e)}")
            return None

    def get_valid_token(self, user):
        """Get a valid access token, refreshing if necessary"""
        try:
            token = PracticePantherToken.objects.get(user=user)

            # Check if token is expired (with 5 minute buffer)
            if token.expires_at <= datetime.now() + timedelta(minutes=5):
                logger.info(
                    f"Token expired for user {user.username}, attempting refresh")
                token = self.refresh_token(user)

            return token
        except PracticePantherToken.DoesNotExist:
            logger.warning(f"No token found for user {user.username}")
            return None


class PracticePantherTimeEntryService:
    """Service to create and manage time entries in PracticePanther"""

    def __init__(self):
        self.base_url = settings.PRACTICE_PANTHER_BASE_URL
        self.oauth_service = PracticePantherOAuthService()

    def create_time_entry(self, user, email_summary_data):
        """Create a time entry in PracticePanther"""
        try:
            # Get valid token
            token = self.oauth_service.get_valid_token(user)
            if not token:
                raise Exception("No valid PracticePanther token available")

            # Get user configuration
            try:
                pp_user = PracticePantherUser.objects.get(user=user)
            except PracticePantherUser.DoesNotExist:
                raise Exception("PracticePanther user configuration not found")

            # Prepare time entry data
            duration_minutes = email_summary_data.get(
                'duration_minutes', settings.DEFAULT_TIME_ENTRY_DURATION_MINUTES)
            hourly_rate = float(
                pp_user.default_hourly_rate or settings.DEFAULT_HOURLY_RATE)

            time_entry_data = {
                'Date': datetime.now().strftime('%Y-%m-%d'),
                'Description': email_summary_data['billable_description'],
                'Hours': round(duration_minutes / 60.0, 2),
                'Rate': hourly_rate,
                'UserId': pp_user.practice_panther_user_id,
            }

            # Add matter if specified
            if pp_user.default_matter_id:
                time_entry_data['MatterId'] = pp_user.default_matter_id

            # Make API request
            headers = {
                'Authorization': f'Bearer {token.access_token}',
                'Content-Type': 'application/json'
            }

            response = requests.post(
                f"{self.base_url}/api/TimeEntry",
                json=time_entry_data,
                headers=headers
            )

            if response.status_code in [200, 201]:
                time_entry_response = response.json()

                # Create local record
                local_time_entry = EmailSummaryTimeEntry.objects.create(
                    user=user,
                    email_subject=email_summary_data.get('subject', ''),
                    email_summary=email_summary_data['summary'],
                    billable_description=email_summary_data['billable_description'],
                    practice_panther_time_entry_id=time_entry_response.get(
                        'Id'),
                    duration_minutes=duration_minutes,
                    hourly_rate=hourly_rate,
                    matter_id=pp_user.default_matter_id,
                    synced_to_practice_panther=True
                )

                logger.info(
                    f"Successfully created time entry {time_entry_response.get('Id')} for user {user.username}")
                return {
                    'success': True,
                    'time_entry_id': time_entry_response.get('Id'),
                    'local_entry_id': local_time_entry.id,
                    'hours': time_entry_data['Hours'],
                    'rate': hourly_rate,
                    'total': round(time_entry_data['Hours'] * hourly_rate, 2)
                }
            else:
                error_msg = f"PracticePanther API error: {response.status_code} - {response.text}"
                logger.error(error_msg)

                # Create local record with sync error
                EmailSummaryTimeEntry.objects.create(
                    user=user,
                    email_subject=email_summary_data.get('subject', ''),
                    email_summary=email_summary_data['summary'],
                    billable_description=email_summary_data['billable_description'],
                    duration_minutes=duration_minutes,
                    hourly_rate=hourly_rate,
                    matter_id=pp_user.default_matter_id,
                    synced_to_practice_panther=False,
                    sync_error=error_msg
                )

                return {
                    'success': False,
                    'error': error_msg
                }

        except Exception as e:
            error_msg = f"Error creating time entry: {str(e)}"
            logger.error(error_msg)
            return {
                'success': False,
                'error': error_msg
            }

    def get_user_matters(self, user):
        """Get list of matters for the user"""
        try:
            token = self.oauth_service.get_valid_token(user)
            if not token:
                return []

            headers = {
                'Authorization': f'Bearer {token.access_token}',
                'Content-Type': 'application/json'
            }

            response = requests.get(
                f"{self.base_url}/api/Matter",
                headers=headers
            )

            if response.status_code == 200:
                return response.json()
            else:
                logger.error(
                    f"Failed to fetch matters: {response.status_code} - {response.text}")
                return []

        except Exception as e:
            logger.error(f"Error fetching matters: {str(e)}")
            return []
