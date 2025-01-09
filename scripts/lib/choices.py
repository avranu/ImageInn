"""

	Metadata:

		File: choices.py
		Project: lib
		Created Date: 19 Aug 2023
		Author: Jess Mann
		Email: jess.a.mann@gmail.com

		-----

		Last Modified: Sat Aug 19 2023
		Modified By: Jess Mann

		-----

		Copyright (c) 2023 Jess Mann
"""
from __future__ import annotations
from enum import Enum
from typing import Any


class Choices(Enum):
	"""
	Standard enum methods to make enums more useful.
	"""

	@classmethod
	def values(cls) -> list[str]:
		"""
		Get a list of all the values of the enum.
		"""
		return [item.value for item in cls]

	@classmethod
	def names(cls) -> list[str]:
		"""
		Get a list of all the names of the enum.
		"""
		return [item.name for item in cls]

	@classmethod
	def has_value(cls, value: str) -> bool:
		"""
		Check if the enum has a value.
		"""
		return value in cls.values()

	@classmethod
	def has_name(cls, name: str) -> bool:
		"""
		Check if the enum has a name.
		"""
		return name in cls.names()

	def __eq__(self, value: Any) -> bool:
		"""
		Allow comparisons with strings.
		"""
		if isinstance(value, str):
			return self.value == value
		return super().__eq__(value)

	def __str__(self) -> str:
		"""
		Allow the enum to be printed as a string.
		"""
		return self.value

	def __repr__(self) -> str:
		"""
		Allow the enum to be printed as a string.
		"""
		return self.value

	def __hash__(self) -> int:
		"""
		Allow the enum to be used as a key in a dict.
		"""
		return hash(self.value)

	def __lt__(self, other: Any) -> bool:
		"""
		Allow comparisons with strings.
		"""
		if isinstance(other, str):
			return self.value < other
		return super().__lt__(other)

	def __le__(self, other: Any) -> bool:
		"""
		Allow comparisons with strings.
		"""
		if isinstance(other, str):
			return self.value <= other
		return super().__le__(other)

	def __gt__(self, other: Any) -> bool:
		"""
		Allow comparisons with strings.
		"""
		if isinstance(other, str):
			return self.value > other
		return super().__gt__(other)

	def __ge__(self, other: Any) -> bool:
		"""
		Allow comparisons with strings.
		"""
		if isinstance(other, str):
			return self.value >= other
		return super().__ge__(other)

	def __ne__(self, other: Any) -> bool:
		"""
		Allow comparisons with strings.
		"""
		if isinstance(other, str):
			return self.value != other
		return super().__ne__(other)

	def __contains__(self, item: Any) -> bool:
		"""
		Allow comparisons with strings.
		"""
		if isinstance(item, str):
			return item in self.value
		return super().__contains__(item)

	def __len__(self) -> int:
		"""
		Allow comparisons with strings.
		"""
		return len(self.value)
