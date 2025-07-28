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
    recipient_email = serializers.EmailField(
        required=False,
        help_text="Email address of the recipient"
    )
    subject = serializers.CharField(
        required=False,
        help_text="Subject line of the email"
    )
    matter_id = serializers.CharField(
        required=False,
        help_text="Clio matter ID to associate the billable entry with"
    )

    def validate_email_content(self, value):
        if not value or len(value.strip()) < 10:
            raise serializers.ValidationError(
                "Email content must be at least 10 characters long")
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
