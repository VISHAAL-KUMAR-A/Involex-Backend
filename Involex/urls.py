from django.urls import path
from .views import (
    EmailSummaryAPIView,
    ClioAuthView,
    ClioCallbackView,
    ClioMattersView,
    TestClioEntryView,
    TestClioUserView,
    ClioLogoutView,
    ClioConfigTestView,
    UserPreferencesView,
    TestEmailAnalysisView,
    DebugClioConnectionView,
    PostmanTimeEntryTestView,
    FetchTimeEntryDetailsView,
    CreateBillableEntryView,
    LatestAIAnalysisView
)

app_name = 'involex'

urlpatterns = [
    path('summarize-email/', EmailSummaryAPIView.as_view(), name='email_summary'),
    path('test-email-analysis/', TestEmailAnalysisView.as_view(),
         name='test_email_analysis'),
    path('clio/auth/', ClioAuthView.as_view(), name='clio_auth'),
    path('clio/callback/', ClioCallbackView.as_view(), name='clio_callback'),
    path('clio/matters/', ClioMattersView.as_view(), name='clio_matters'),
    path('clio/test-entry/', TestClioEntryView.as_view(), name='test_clio_entry'),
    path('clio/test-user/', TestClioUserView.as_view(), name='test_clio_user'),
    path('clio/logout/', ClioLogoutView.as_view(), name='clio_logout'),
    path('clio/config-test/', ClioConfigTestView.as_view(), name='clio_config_test'),
    path('clio/preferences/', UserPreferencesView.as_view(),
         name='user_preferences'),
    path('clio/debug/', DebugClioConnectionView.as_view(),
         name='debug_clio_connection'),
    path('clio/postman-test/', PostmanTimeEntryTestView.as_view(),
         name='postman_time_entry_test'),
    path('clio/fetch-entry/', FetchTimeEntryDetailsView.as_view(),
         name='fetch_time_entry_details'),
    path('clio/create-billable/', CreateBillableEntryView.as_view(),
         name='create_billable_entry'),
    path('clio/latest-ai-analysis/', LatestAIAnalysisView.as_view(),
         name='latest_ai_analysis'),
]
