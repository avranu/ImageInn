from django.db import models

class File(models.Model):
    path = models.TextField(unique=True)
    checksum = models.CharField(max_length=64)
    duplicate_count = models.IntegerField(default=0)
    duplicates = models.ManyToManyField('self')
