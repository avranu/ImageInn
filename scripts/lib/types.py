from typing import Protocol, runtime_checkable

# Define typealias for Number
@runtime_checkable
class Number(Protocol):
    def __float__(self) -> float:
        ...