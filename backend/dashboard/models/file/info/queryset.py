from __future__ import annotations
from djangofoundry import models

class QuerySet(models.QuerySet):
	pass

class Manager(models.Manager.from_queryset(QuerySet)):
	pass