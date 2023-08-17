from __future__ import annotations
from djangofoundry import models
from .model import FileInfo
from .serializer import Serializer

class ViewSet(models.ViewSet):
	queryset = FileInfo.objects.all()
	serializer_class = Serializer
