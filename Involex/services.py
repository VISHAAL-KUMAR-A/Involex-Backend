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
        if self.user.token_expires_at <= timezone.now():
            self._refresh_token()

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
            self.user.token_expires_at = timezone.now() + timedelta(seconds=data["expires_in"])
            self.user.save()
        else:
            raise Exception("Failed to refresh Clio access token")

    def _make_request(self, method, endpoint, data=None):
        """Make authenticated request to Clio API"""
        headers = {
            "Authorization": f"Bearer {self.user.access_token}",
            "Content-Type": "application/json"
        }

        url = f"{self.base_url}/api/v4/{endpoint}"

        if method == "GET":
            response = requests.get(url, headers=headers)
        elif method == "POST":
            response = requests.post(url, headers=headers, json=data)
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")

        if response.status_code in [200, 201]:
            return response.json()
        else:
            raise Exception(f"Clio API error: {response.text}")

    def create_time_entry(self, matter_id, date, duration, description, note=None):
        """Create a billable time entry in Clio"""
        data = {
            "data": {
                "type": "time_entries",
                "attributes": {
                    "date": date.strftime("%Y-%m-%d"),
                    "duration": duration,  # in seconds
                    "description": description,
                    "note": note or "",
                    "quantity": duration / 3600.0,  # Convert seconds to hours
                    "type": "TimeEntry"
                },
                "relationships": {
                    "matter": {
                        "data": {
                            "type": "matters",
                            "id": str(matter_id)
                        }
                    }
                }
            }
        }

        return self._make_request("POST", "time_entries", data)

    def get_matters(self, status="open"):
        """Get list of matters from Clio"""
        response = self._make_request("GET", f"matters?status={status}")
        return response.get("data", [])
