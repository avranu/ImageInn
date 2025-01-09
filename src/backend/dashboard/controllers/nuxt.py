"""
	This module passes the controller logic off to a Nuxt frontend.

	Metadata:

		File: frontend.py
		Author: Jess Mann

		-----

		Modified By: Jess Mann

"""
# Generic imports
from __future__ import annotations
from djangofoundry.controllers import ListController

class NuxtController(ListController):
	"""
	This controller passes routing responsibility off to the Nuxt frontend.
	"""
	# The template that contains our nuxt js code.
	template_name = 'dashboard/nuxt.html'

	def get_queryset(self):
		"""
		Do not make any queries or return any data. Nuxt will connect via our REST API to get the data it needs.

		Returns:
			An empty object.
		"""
		return {}
