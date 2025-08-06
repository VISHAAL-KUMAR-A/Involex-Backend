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

        logger.info(f"🔧 Token expires at: {self.user.token_expires_at}")
        logger.info(f"🔧 Current time: {timezone.now()}")
        logger.info(
            f"🔧 Token expired: {self.user.token_expires_at <= timezone.now()}")

        if self.user.token_expires_at <= timezone.now():
            logger.info("🔧 Token expired, refreshing...")
            self._refresh_token()
        else:
            logger.info("✅ Token is still valid")

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

        logger.info(f"🔧 Creating time entry for matter_id: {matter_id}")

        # First, let's verify the matter exists
        try:
            matter_check = self._make_request("GET", f"matters/{matter_id}")
            logger.info(
                f"✅ Matter exists: {matter_check.get('data', {}).get('display_number', 'Unknown')}")
        except Exception as e:
            logger.error(f"❌ Matter verification failed: {str(e)}")
            # Let's try to get all matters to see what's available
            try:
                all_matters = self._make_request("GET", "matters")
                logger.info(
                    f"Available matters: {[m.get('id') for m in all_matters.get('data', [])]}")
            except Exception as e2:
                logger.error(f"❌ Could not fetch matters: {str(e2)}")
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

        try:
            response = self._make_request("POST", "activities", data)
            logger.info(f"SUCCESS: Time entry created successfully")
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
