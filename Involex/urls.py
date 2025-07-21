from django.urls import path
from .views import EmailSummaryAPIView

app_name = 'involex'

urlpatterns = [
    path('summarize-email/', EmailSummaryAPIView.as_view(), name='email_summary'),
]
