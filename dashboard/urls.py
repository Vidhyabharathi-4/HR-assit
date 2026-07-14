from django.urls import path
from .views import (
    IndexView,
    ResumeUploadAPI,
    ResumeListAPI,
    ResumeDetailAPI,
    GithubProxyAPI
)

urlpatterns = [
    path('', IndexView.as_view(), name='dashboard_index'),
    path('api/resume/upload/', ResumeUploadAPI.as_view(), name='api_resume_upload'),
    path('api/resume/list/', ResumeListAPI.as_view(), name='api_resume_list'),
    path('api/resume/<int:pk>/', ResumeDetailAPI.as_view(), name='api_resume_detail'),
    path('api/github/check/', GithubProxyAPI.as_view(), name='api_github_check'),
]
