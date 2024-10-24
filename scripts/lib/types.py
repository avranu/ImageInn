"""*********************************************************************************************************************
*                                                                                                                      *
*                                                                                                                      *
*                                                                                                                      *
*                                                                                                                      *
* -------------------------------------------------------------------------------------------------------------------- *
*                                                                                                                      *
*    METADATA:                                                                                                         *
*                                                                                                                      *
*        File:    types.py                                                                                             *
*        Project: imageinn                                                                                             *
*        Version: 0.1.0                                                                                                *
*        Created: 2024-07-20                                                                                           *
*        Author:  Jess Mann                                                                                            *
*        Email:   jess.a.mann@gmail.com                                                                                *
*        Copyright (c) 2024 Jess Mann                                                                                  *
*                                                                                                                      *
* -------------------------------------------------------------------------------------------------------------------- *
*                                                                                                                      *
*    LAST MODIFIED:                                                                                                    *
*                                                                                                                      *
*        2024-10-23     By Jess Mann                                                                                   *
*                                                                                                                      *
*********************************************************************************************************************"""
from typing import Protocol, runtime_checkable

# Define typealias for Number
@runtime_checkable
class Number(Protocol):
    def __float__(self) -> float:
        ...

# Define a Protocol for alive_bar()
class ProgressBar(Protocol):
    def __call__(self, *args, **kwargs) -> None:
        ...

    def text(self, text: str) -> None:
        ...

# Define a few colors for logging and printing purposes
RED = '\033[91m'
GREEN = '\033[92m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
PURPLE = '\033[95m'
RESET = '\033[0m'