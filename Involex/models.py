from django.db import models
from django.contrib.auth.models import User

# Create your models here.


class PracticePantherToken(models.Model):
    """Store PracticePanther OAuth tokens for users"""
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name='practice_panther_token')
    access_token = models.TextField(help_text="OAuth access token")
    refresh_token = models.TextField(help_text="OAuth refresh token")
    expires_at = models.DateTimeField(
        help_text="When the access token expires")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"PracticePanther Token for {self.user.username}"

    class Meta:
        verbose_name = "PracticePanther Token"
        verbose_name_plural = "PracticePanther Tokens"


class PracticePantherUser(models.Model):
    """Store PracticePanther user configuration"""
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name='practice_panther_user')
    practice_panther_user_id = models.CharField(
        max_length=255, help_text="PracticePanther User ID")
    default_matter_id = models.CharField(
        max_length=255, blank=True, null=True, help_text="Default matter for time entries")
    default_hourly_rate = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00, help_text="Default hourly rate")
    auto_create_time_entries = models.BooleanField(
        default=True, help_text="Automatically create time entries for email summaries")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"PracticePanther User: {self.user.username}"

    class Meta:
        verbose_name = "PracticePanther User"
        verbose_name_plural = "PracticePanther Users"


class EmailSummaryTimeEntry(models.Model):
    """Track time entries created from email summaries"""
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    email_subject = models.CharField(max_length=500, blank=True)
    email_summary = models.TextField()
    billable_description = models.TextField()
    practice_panther_time_entry_id = models.CharField(
        max_length=255, blank=True, null=True)
    duration_minutes = models.IntegerField(
        default=15, help_text="Duration in minutes")
    hourly_rate = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00)
    matter_id = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    synced_to_practice_panther = models.BooleanField(default=False)
    sync_error = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Time Entry: {self.email_subject[:50]} - {self.user.username}"

    class Meta:
        verbose_name = "Email Summary Time Entry"
        verbose_name_plural = "Email Summary Time Entries"
        ordering = ['-created_at']
