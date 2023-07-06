from __future__ import annotations
from django.db.models import CASCADE, Index
from djangofoundry import models
from .queryset import Manager

class FileChecksum(models.Model):
    checksum = models.CharField(max_length=64)
    created = models.InsertedNowField()
    updated = models.UpdatedNowField()

    file = models.ForeignKey(
        'FileInfo', 
        on_delete=CASCADE,
        related_name='checksums',
    )

    objects = Manager()

    class Meta(models.Model.Meta):
        db_table = 'dashboard_file_checksum'
        ordering = ['created']

        indexes = [
            Index(fields=['file', 'created'], name='most_recent_checksum'),
        ]