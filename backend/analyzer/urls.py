from django.urls import path
from . import views

urlpatterns = [
    path("", views.health),
    path("api/analyze/", views.AnalyzeView.as_view()),
]
