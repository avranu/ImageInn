from rest_framework import viewsets
from rest_framework.response import Response
from .SD import SDCards
from .serializer import Serializer

class ViewSet(viewsets.ViewSet):
	basename : str = 'sd'

	def list(self, request):
		sd_cards = SDCards()
		data = sd_cards.get_list()
		serializer = Serializer(data, many=True)
		return Response(serializer.data)

	def retrieve(self, request, pk=None):
		sd_cards = SDCards()
		data = sd_cards.get_info(pk)
		serializer = Serializer(data)
		return Response(serializer.data)
