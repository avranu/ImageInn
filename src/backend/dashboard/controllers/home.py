"""

	Metadata:

		File: home.py
		Author: Jess Mann
		Email: jmann@osc.ny.gov

		-----

		Modified By: Jess Mann

		-----
"""
# Generic imports
from __future__ import annotations
from djangofoundry.controllers import ListController

class IndexController(ListController):
	template_name = 'dashboard/homepage.html'
	context_object_name = 'case_list'

	def get_queryset(self):
		return {}
