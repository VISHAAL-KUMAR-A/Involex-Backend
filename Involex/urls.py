from django.urls import path
from .views import EmailSummaryAPIView, ClioAuthView, ClioCallbackView, ClioMattersView

app_name = 'involex'

urlpatterns = [
    path('summarize-email/', EmailSummaryAPIView.as_view(), name='email_summary'),
    path('clio/auth/', ClioAuthView.as_view(), name='clio_auth'),
    path('clio/callback/', ClioCallbackView.as_view(), name='clio_callback'),
    path('clio/matters/', ClioMattersView.as_view(), name='clio_matters'),
]
