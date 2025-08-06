import json
import requests
from datetime import datetime, timedelta
from django.conf import settings
from django.utils import timezone
from .models import ClioUser, ClioMatter


class ClioAPIService:
    REGIONS = {
        'NA': 'https://app.clio.com',
        'EU': 'https://eu.app.clio.com',
        'CA': 'https://ca.app.clio.com'
    }

    def __init__(self, user_email):
        self.user = ClioUser.objects.get(email=user_email)
        self._check_token_expiry()
        # Default to NA if not specified
        self.base_url = self.REGIONS.get(self.user.region, self.REGIONS['NA'])

    def _check_token_expiry(self):
        """Check if token is expired and refresh if needed"""
        import logging
        logger = logging.getLogger(__name__)

        logger.info(f"DEBUG: Token expires at: {self.user.token_expires_at}")
        logger.info(f"DEBUG: Current time: {timezone.now()}")
        logger.info(
            f"DEBUG: Token expired: {self.user.token_expires_at <= timezone.now()}")

        if self.user.token_expires_at <= timezone.now():
            logger.info("DEBUG: Token expired, refreshing...")
            self._refresh_token()
        else:
            logger.info("SUCCESS: Token is still valid")

    def _refresh_token(self):
        """Refresh the access token using refresh token"""
        response = requests.post(
            f"{self.base_url}/oauth/token",
            data={
                "client_id": settings.CLIO_CLIENT_ID,
                "client_secret": settings.CLIO_CLIENT_SECRET,
                "grant_type": "refresh_token",
                "refresh_token": self.user.refresh_token
            }
        )

        if response.status_code == 200:
            data = response.json()
            self.user.access_token = data["access_token"]
            self.user.refresh_token = data["refresh_token"]
            self.user.token_expires_at = timezone.now(
            ) + timedelta(seconds=data["expires_in"])
            self.user.save()
        else:
            raise Exception("Failed to refresh Clio access token")

    def _make_request(self, method, endpoint, data=None):
        """Make authenticated request to Clio API"""
        import logging
        logger = logging.getLogger(__name__)

        headers = {
            "Authorization": f"Bearer {self.user.access_token}",
            "Content-Type": "application/json"
        }

        url = f"{self.base_url}/api/v4/{endpoint}"

        logger.info(f"CLIO API: Making {method} request to {url}")
        logger.info(f"CLIO API: Headers: {headers}")
        if data:
            logger.info(f"CLIO API: Request data: {data}")

        if method == "GET":
            response = requests.get(url, headers=headers)
        elif method == "POST":
            response = requests.post(url, headers=headers, json=data)
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")

        logger.info(f"CLIO API: Response status: {response.status_code}")
        logger.info(f"CLIO API: Response headers: {dict(response.headers)}")
        logger.info(f"CLIO API: Response text: {response.text[:500]}...")

        if response.status_code in [200, 201]:
            return response.json()
        else:
            raise Exception(f"Clio API error: {response.text}")

    def create_time_entry(self, matter_id, date, duration, description, note=None, hourly_rate=None):
        """Create a billable time entry in Clio"""
        import logging
        logger = logging.getLogger(__name__)

        logger.info(f"DEBUG: Creating time entry for matter_id: {matter_id}")

        # First, let's verify the matter exists
        try:
            matter_check = self._make_request("GET", f"matters/{matter_id}")
            logger.info(
                f"SUCCESS: Matter exists: {matter_check.get('data', {}).get('display_number', 'Unknown')}")
        except Exception as e:
            logger.error(f"ERROR: Matter verification failed: {str(e)}")
            # Let's try to get all matters to see what's available
            try:
                all_matters = self._make_request("GET", "matters")
                logger.info(
                    f"Available matters: {[m.get('id') for m in all_matters.get('data', [])]}")
            except Exception as e2:
                logger.error(f"ERROR: Could not fetch matters: {str(e2)}")
            raise Exception(f"Matter {matter_id} not found or accessible")

        # Use Clio API v4 format as shown in documentation
        # Reference: https://docs.developers.clio.com/api-docs/fields/
        data = {
            "data": {
                "date": date.strftime("%Y-%m-%d"),
                "quantity": duration,  # Duration in seconds
                "description": description,
                "type": "TimeEntry",  # Required type field
                "note": note or "",
                # Include price (hourly rate) if provided
                **({"price": hourly_rate} if hourly_rate else {}),
                "relationships": {
                    "matter": {
                        "data": {
                            "type": "matters",
                            "id": str(matter_id)
                        }
                    },
                    "user": {
                        "data": {
                            "type": "users",
                            "id": str(self.user.clio_user_id)
                        }
                    }
                }
            }
        }

        logger.info(
            f"CLIO API: Time entry data being sent to POST /activities:")
        logger.info(f"CLIO API: JSON payload: {json.dumps(data, indent=2)}")

        # DEBUG: Log the specific fields we're concerned about (no emoji for Windows)
        logger.info(f"CLIO SEND DEBUG: Fields being sent to Clio:")
        logger.info(f"   DESCRIPTION TO CLIO: '{data['data']['description']}'")
        logger.info(f"   NOTE TO CLIO: '{data['data']['note']}'")
        logger.info(
            f"   Matter ID: '{data['data']['relationships']['matter']['data']['id']}'")
        logger.info(
            f"   User ID: '{data['data']['relationships']['user']['data']['id']}'")

        # Additional validation
        if "Processed via Involex AI analysis" in data['data']['description']:
            logger.error(
                f"CRITICAL ERROR: Note content found in description field being sent to Clio!")
            logger.error(
                f"   Description should contain AI analysis, not note text!")

        try:
            response = self._make_request("POST", "activities", data)
            logger.info(f"SUCCESS: Time entry created successfully")

            # DEBUG: Log what Clio returned - check both root level and attributes
            if response and 'data' in response:
                clio_data = response['data']

                # Try root level first (older API format)
                returned_description = clio_data.get(
                    'description', 'NOT_FOUND_ROOT')
                returned_note = clio_data.get('note', 'NOT_FOUND_ROOT')

                # Try attributes field (newer API format)
                if 'attributes' in clio_data:
                    attributes = clio_data['attributes']
                    returned_description_attr = attributes.get(
                        'description', 'NOT_FOUND_ATTR')
                    returned_note_attr = attributes.get(
                        'note', 'NOT_FOUND_ATTR')
                    logger.info(
                        f"   Description in attributes: '{returned_description_attr}'")
                    logger.info(
                        f"   Note in attributes: '{returned_note_attr}'")

                returned_matter_id = None

                # Check if matter relationship exists in response
                if 'relationships' in clio_data and 'matter' in clio_data['relationships']:
                    matter_data = clio_data['relationships']['matter']
                    if 'data' in matter_data:
                        returned_matter_id = matter_data['data'].get(
                            'id', 'NOT_FOUND')

                logger.info(f"DEBUG: Clio returned the following fields:")
                logger.info(f"   Description (root): '{returned_description}'")
                logger.info(f"   Note (root): '{returned_note}'")
                logger.info(f"   Matter ID: '{returned_matter_id}'")
                logger.info(
                    f"   Entry ID: '{clio_data.get('id', 'NOT_FOUND')}'")

                # Log full response structure for debugging
                logger.info(f"DEBUG: Full Clio response structure:")
                logger.info(f"{json.dumps(response, indent=2)}")

            return response
        except Exception as e:
            logger.error(
                f"FAILED: Time entry creation failed with error: {str(e)}")
            logger.error(f"DEBUG: Full error details: {repr(e)}")
            raise

    def get_matters(self, status="open"):
        """Get list of matters from Clio"""
        import logging
        logger = logging.getLogger(__name__)

        # Try to get more detailed matter information by including relationships
        response = self._make_request(
            "GET", f"matters?status={status}&include=client")
        matters_data = response.get("data", [])

        # Add debugging to see what data we're getting
        logger.info(f"Raw matters response: {response}")
        logger.info(f"Number of matters returned: {len(matters_data)}")
        if matters_data:
            logger.info(f"First matter structure: {matters_data[0]}")

        return matters_data
