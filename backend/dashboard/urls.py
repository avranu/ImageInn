# Generic imports
from __future__ import annotations
# Django imports
from django.urls import path, include, re_path
# 3rd Party imports
from rest_framework import routers
# App Imports
from dashboard.controllers import react

app_name = 'dashboard'

# Define all our REST API routes
routes = {
	#'chart': api.ChartViewSet,
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
	path('rest/', include(router.urls)),

	# Send everything else to react.
	re_path(r'^.*$', react.ReactController.as_view(), name="react"),
]
