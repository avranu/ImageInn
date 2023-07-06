from __future__ import annotations
from django.db.models import CASCADE, ManyToManyField, Index
from djangofoundry import models
import os

class FileInfo(models.Model):
    path = models.TextField(unique=True)
    created = models.InsertedNowField()
    updated = models.UpdatedNowField()

    # RELATIONSHIPS
    # checksums : FileChecksum

    def exists(self):
        return os.path.exists(self.path)

    class Meta(models.Model.Meta):
        db_table = 'dashboard_file_info'
        ordering = ['path']