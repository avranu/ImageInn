from djangofoundry import models
from .model import FileChecksum

class Serializer(models.Serializer):
    class Meta(models.Serializer.Meta):
        model = FileChecksum
        fields = ['checksum', 'file', 'created', 'updated']