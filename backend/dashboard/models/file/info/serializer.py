from djangofoundry import models
from .model import FileInfo

class Serializer(models.Serializer):
	class Meta(models.Serializer.Meta):
		model = FileInfo
		fields = ['path', 'checksums', 'created', 'updated']