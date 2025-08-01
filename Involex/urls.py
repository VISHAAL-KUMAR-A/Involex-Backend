from django.urls import path
from .views import (
    EmailSummaryAPIView,
    ClioAuthView,
    ClioCallbackView,
    ClioMattersView,
    TestClioEntryView,
    TestClioUserView,
    ClioLogoutView,
    ClioConfigTestView
)

app_name = 'involex'

urlpatterns = [
    path('summarize-email/', EmailSummaryAPIView.as_view(), name='email_summary'),
    path('clio/auth/', ClioAuthView.as_view(), name='clio_auth'),
    path('clio/callback/', ClioCallbackView.as_view(), name='clio_callback'),
    path('clio/matters/', ClioMattersView.as_view(), name='clio_matters'),
    path('clio/test-entry/', TestClioEntryView.as_view(), name='test_clio_entry'),
    path('clio/test-user/', TestClioUserView.as_view(), name='test_clio_user'),
    path('clio/logout/', ClioLogoutView.as_view(), name='clio_logout'),
    path('clio/config-test/', ClioConfigTestView.as_view(), name='clio_config_test'),
]
