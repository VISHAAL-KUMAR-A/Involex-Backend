from rest_framework import serializers


class EmailSummarySerializer(serializers.Serializer):
    email_content = serializers.CharField(
        help_text="The full content of the email to be summarized",
        style={'base_template': 'textarea.html'}
    )
    sender_email = serializers.EmailField(
        required=False,
        help_text="Email address of the sender"
    )
    # Accept 'sender' as an alternative to 'sender_email' for frontend compatibility
    sender = serializers.EmailField(
        required=False,
        help_text="Email address of the sender (alternative field name)"
    )
    recipient_email = serializers.EmailField(
        required=False,
        help_text="Email address of the recipient"
    )
    # Accept 'recipient' as an alternative to 'recipient_email' for frontend compatibility
    recipient = serializers.EmailField(
        required=False,
        help_text="Email address of the recipient (alternative field name)"
    )
    subject = serializers.CharField(
        required=False,
        help_text="Subject line of the email"
    )
    matter_id = serializers.CharField(
        required=False,
        help_text="Clio matter ID to associate the billable entry with"
    )
    region = serializers.CharField(
        required=False,
        help_text="Clio region (NA, EU, or CA)",
        default='NA'
    )

    def validate_email_content(self, value):
        if not value or len(value.strip()) < 10:
            raise serializers.ValidationError(
                "Email content must be at least 10 characters long")
        return value

    def validate_region(self, value):
        value = value.upper()
        if value not in ['NA', 'EU', 'CA']:
            return 'NA'
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
    clio_entry_created = serializers.BooleanField(
        help_text="Whether a billable entry was created in Clio")
    clio_entry_id = serializers.CharField(
        required=False, allow_null=True,
        help_text="ID of the created Clio billable entry")
    clio_entry_error = serializers.CharField(
        required=False, allow_null=True,
        help_text="Error message if Clio entry creation failed")
