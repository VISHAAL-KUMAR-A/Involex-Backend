from django.urls import path
from .views import EmailSummaryAPIView, summarize_email_debug_view

app_name = 'involex'

urlpatterns = [
    path('summarize-email/', EmailSummaryAPIView.as_view(), name='email_summary'),
    # DEBUG URL - Remove after debugging
    path('debug-summarize-email/', summarize_email_debug_view,
         name='debug_email_summary'),
]
