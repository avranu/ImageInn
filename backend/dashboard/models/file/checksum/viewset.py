from __future__ import annotations
from djangofoundry import models
from .model import FileChecksum
from .serializer import Serializer

class ViewSet(models.ViewSet):
    queryset = FileChecksum.objects.all()
    serializer_class = Serializer
