# Generic imports
from __future__ import annotations
# Django imports
from django.urls import path, include
# 3rd Party imports
from rest_framework import routers
# App Imports
from dashboard.services import SDViewSet
from backend.dashboard.models import FileInfoViewSet, FileChecksumViewSet

app_name = 'dashboard'

# Define all our REST API routes
routes = {
	#'chart': api.ChartViewSet,
	'sd': SDViewSet,
	'file': FileInfoViewSet,
	'file_checksum': FileChecksumViewSet,
}
# Use the default router to define endpoints
router = routers.DefaultRouter()
# Register each viewset with the router
for route, viewset in routes.items():
	if hasattr(viewset, 'basename'):
		router.register(route, viewset, basename = getattr(viewset, 'basename'))
	else:
		router.register(route, viewset)

urlpatterns = [
	# ex: /api/
	path('api/', include(router.urls)),

	# Send everything else to... todo
]
