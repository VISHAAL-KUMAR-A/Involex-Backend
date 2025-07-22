from django.urls import path
from .views import (
    EmailSummaryAPIView, summarize_email_debug_view,
    PracticePantherOAuthInitView, PracticePantherOAuthCallbackView,
    PracticePantherUserConfigView, PracticePantherMattersView,
    TimeEntryListView, CreateTimeEntryView,
    login_view, user_status_view, register_view
)

app_name = 'involex'

urlpatterns = [
    # Email summarization
    path('summarize-email/', EmailSummaryAPIView.as_view(), name='email_summary'),

    # Authentication
    path('auth/login/', login_view, name='login'),
    path('auth/register/', register_view, name='register'),
    path('auth/status/', user_status_view, name='user_status'),

    # PracticePanther OAuth
    path('practice-panther/oauth/init/',
         PracticePantherOAuthInitView.as_view(), name='pp_oauth_init'),
    path('practice-panther/oauth/callback/',
         PracticePantherOAuthCallbackView.as_view(), name='pp_oauth_callback'),

    # PracticePanther Configuration
    path('practice-panther/config/',
         PracticePantherUserConfigView.as_view(), name='pp_user_config'),
    path('practice-panther/matters/',
         PracticePantherMattersView.as_view(), name='pp_matters'),

    # Time Entry Management
    path('time-entries/', TimeEntryListView.as_view(), name='time_entries_list'),
    path('time-entries/create/', CreateTimeEntryView.as_view(),
         name='create_time_entry'),

    # DEBUG URL - Remove after debugging
    path('debug-summarize-email/', summarize_email_debug_view,
         name='debug_email_summary'),
]
