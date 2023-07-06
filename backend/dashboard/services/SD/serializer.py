from rest_framework import serializers, viewsets
from .SD import SDCards

class Serializer(serializers.Serializer):
    path = serializers.CharField()
    total = serializers.IntegerField()
    used = serializers.IntegerField()
    free = serializers.IntegerField()
    num_files = serializers.IntegerField()
    num_dirs = serializers.IntegerField()