from __future__ import annotations
from django.shortcuts import render
from backend.dashboard.services import SDCards

from djangofoundry.controllers import GenericController

class BaseSDCardView(GenericController):
	def setup(self, request, *args, **kwargs):
		super().setup(request, *args, **kwargs)
		self.sd_cards = SDCards()

class IndexView(BaseSDCardView):
	def get(self, request):
		card_list = self.sd_cards.get_list()
		return render(request, 'dashboard/sd_cards/index.html', {'sd_cards': card_list})

class CopyView(BaseSDCardView):
	def get(self, request, sd_card_path):
		card = self.sd_cards.get_info(sd_card_path)
		return render(request, 'dashboard/sd_cards/detail.html', {'sd_card': card})

	def post(self, request, sd_card_path):
		network_path = request.POST.get('network_path')
		backup_network_path = request.POST.get('backup_network_path')
		self.sd_cards.copy_sd_card(sd_card_path, network_path, backup_network_path)
		return render(request, 'dashboard/sd_cards/copy.html', {'sd_card_path': sd_card_path})