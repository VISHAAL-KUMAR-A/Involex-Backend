from django.contrib import admin
from .models import PracticePantherToken, PracticePantherUser, EmailSummaryTimeEntry

# Register your models here.


@admin.register(PracticePantherToken)
class PracticePantherTokenAdmin(admin.ModelAdmin):
    list_display = ['user', 'expires_at', 'created_at', 'updated_at']
    list_filter = ['expires_at', 'created_at']
    search_fields = ['user__username', 'user__email']
    readonly_fields = ['created_at', 'updated_at']

    fieldsets = (
        ('User Information', {
            'fields': ('user',)
        }),
        ('Token Details', {
            'fields': ('access_token', 'refresh_token', 'expires_at'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(PracticePantherUser)
class PracticePantherUserAdmin(admin.ModelAdmin):
    list_display = ['user', 'practice_panther_user_id',
                    'default_hourly_rate', 'auto_create_time_entries', 'created_at']
    list_filter = ['auto_create_time_entries', 'created_at']
    search_fields = ['user__username',
                     'user__email', 'practice_panther_user_id']
    readonly_fields = ['created_at', 'updated_at']

    fieldsets = (
        ('User Information', {
            'fields': ('user', 'practice_panther_user_id')
        }),
        ('Default Settings', {
            'fields': ('default_matter_id', 'default_hourly_rate', 'auto_create_time_entries')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(EmailSummaryTimeEntry)
class EmailSummaryTimeEntryAdmin(admin.ModelAdmin):
    list_display = [
        'user', 'email_subject_short', 'duration_minutes', 'hourly_rate',
        'synced_to_practice_panther', 'created_at'
    ]
    list_filter = [
        'synced_to_practice_panther', 'created_at', 'duration_minutes'
    ]
    search_fields = [
        'user__username', 'user__email', 'email_subject',
        'practice_panther_time_entry_id', 'matter_id'
    ]
    readonly_fields = ['created_at']

    fieldsets = (
        ('User and Email Information', {
            'fields': ('user', 'email_subject', 'email_summary')
        }),
        ('Time Entry Details', {
            'fields': ('billable_description', 'duration_minutes', 'hourly_rate', 'matter_id')
        }),
        ('PracticePanther Sync', {
            'fields': ('practice_panther_time_entry_id', 'synced_to_practice_panther', 'sync_error')
        }),
        ('Timestamps', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )

    def email_subject_short(self, obj):
        """Return a shortened version of the email subject"""
        if obj.email_subject:
            return obj.email_subject[:50] + "..." if len(obj.email_subject) > 50 else obj.email_subject
        return "No subject"
    email_subject_short.short_description = "Email Subject"

    def get_queryset(self, request):
        """Optimize queryset with select_related"""
        return super().get_queryset(request).select_related('user')
