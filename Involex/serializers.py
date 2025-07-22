from rest_framework import serializers
from .models import PracticePantherUser, EmailSummaryTimeEntry


class EmailSummarySerializer(serializers.Serializer):
    email_content = serializers.CharField(
        help_text="The full content of the email to be summarized",
        style={'base_template': 'textarea.html'}
    )
    sender_email = serializers.EmailField(
        required=False,
        help_text="Email address of the sender"
    )
    recipient_email = serializers.EmailField(
        required=False,
        help_text="Email address of the recipient"
    )
    subject = serializers.CharField(
        required=False,
        help_text="Subject line of the email"
    )
    duration_minutes = serializers.IntegerField(
        required=False,
        default=15,
        help_text="Duration in minutes for the time entry (default: 15)"
    )
    matter_id = serializers.CharField(
        required=False,
        help_text="PracticePanther Matter ID for this time entry"
    )
    create_time_entry = serializers.BooleanField(
        default=True,
        help_text="Whether to create a time entry in PracticePanther (default: True)"
    )

    def validate_email_content(self, value):
        if not value or len(value.strip()) < 10:
            raise serializers.ValidationError(
                "Email content must be at least 10 characters long")
        return value

    def validate_duration_minutes(self, value):
        if value and (value < 1 or value > 480):  # Max 8 hours
            raise serializers.ValidationError(
                "Duration must be between 1 and 480 minutes")
        return value


class EmailSummaryResponseSerializer(serializers.Serializer):
    summary = serializers.CharField(
        help_text="AI-generated summary of the email")
    word_count_original = serializers.IntegerField(
        help_text="Word count of original email")
    word_count_summary = serializers.IntegerField(
        help_text="Word count of summary")
    billable_description = serializers.CharField(
        help_text="Formatted billable entry description")
    processing_time = serializers.FloatField(
        help_text="Time taken to process the request in seconds")
    time_entry_created = serializers.BooleanField(
        help_text="Whether a time entry was created in PracticePanther")
    time_entry_details = serializers.DictField(
        required=False,
        help_text="Details of the created time entry"
    )


class PracticePantherUserSerializer(serializers.ModelSerializer):
    """Serializer for PracticePanther user configuration"""

    class Meta:
        model = PracticePantherUser
        fields = [
            'practice_panther_user_id',
            'default_matter_id',
            'default_hourly_rate',
            'auto_create_time_entries'
        ]
        extra_kwargs = {
            'practice_panther_user_id': {'required': True}
        }

    def validate_default_hourly_rate(self, value):
        if value < 0:
            raise serializers.ValidationError("Hourly rate cannot be negative")
        return value


class EmailSummaryTimeEntrySerializer(serializers.ModelSerializer):
    """Serializer for viewing time entries created from email summaries"""

    class Meta:
        model = EmailSummaryTimeEntry
        fields = [
            'id',
            'email_subject',
            'email_summary',
            'billable_description',
            'practice_panther_time_entry_id',
            'duration_minutes',
            'hourly_rate',
            'matter_id',
            'created_at',
            'synced_to_practice_panther',
            'sync_error'
        ]
        read_only_fields = ['id', 'created_at']


class OAuthCallbackSerializer(serializers.Serializer):
    """Serializer for OAuth callback data"""
    code = serializers.CharField(
        help_text="Authorization code from PracticePanther OAuth"
    )
    state = serializers.CharField(
        required=False,
        help_text="State parameter from OAuth flow"
    )


class MatterSerializer(serializers.Serializer):
    """Serializer for PracticePanther Matter objects"""
    Id = serializers.CharField(help_text="Matter ID")
    Name = serializers.CharField(help_text="Matter name")
    ClientName = serializers.CharField(help_text="Client name", required=False)
    Description = serializers.CharField(
        help_text="Matter description", required=False)


class TimeEntryCreateSerializer(serializers.Serializer):
    """Serializer for creating standalone time entries"""
    description = serializers.CharField(
        help_text="Description of the work performed"
    )
    duration_minutes = serializers.IntegerField(
        help_text="Duration in minutes"
    )
    matter_id = serializers.CharField(
        required=False,
        help_text="PracticePanther Matter ID"
    )
    hourly_rate = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
        help_text="Hourly rate (defaults to user's default rate)"
    )
    date = serializers.DateField(
        required=False,
        help_text="Date of the work (defaults to today)"
    )

    def validate_duration_minutes(self, value):
        if value < 1 or value > 480:  # Max 8 hours
            raise serializers.ValidationError(
                "Duration must be between 1 and 480 minutes")
        return value
