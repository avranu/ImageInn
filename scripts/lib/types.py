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
    total : int
    
    def __call__(self, *args, **kwargs) -> None:
        ...

    def text(self, text: str) -> None:
        ...


# Styles
RESET = '\033[0m'
BOLD = '\033[1m'
DIM = '\033[2m'
ITALIC = '\033[3m'
UNDERLINE = '\033[4m'
BLINK = '\033[5m'
FAST_BLINK = '\033[6m'
REVERSE = '\033[7m'
HIDDEN = '\033[8m'

# Define a few colors for logging and printing purposes
ANSI_BLACK = '\033[90m'
ANSI_RED = '\033[91m'
ANSI_GREEN = '\033[92m'
ANSI_YELLOW = '\033[93m'
ANSI_BLUE = '\033[94m'
ANSI_PURPLE = '\033[95m'
ANSI_CYAN = '\033[96m'
ANSI_WHITE = '\033[97m'

# Background Colors
BG_BLACK = '\033[40m'
BG_RED = '\033[41m'
BG_GREEN = '\033[42m'
BG_YELLOW = '\033[43m'
BG_BLUE = '\033[44m'
BG_PURPLE = '\033[45m'
BG_CYAN = '\033[46m'
BG_WHITE = '\033[47m'

# By default, our colors should be dim
BLACK = f'{RESET}{DIM}{ANSI_BLACK}'
RED = f'{RESET}{DIM}{ANSI_RED}'
GREEN = f'{RESET}{DIM}{ANSI_GREEN}'
YELLOW = f'{RESET}{DIM}{ANSI_YELLOW}'
BLUE = f'{RESET}{DIM}{ANSI_BLUE}'
PURPLE = f'{RESET}{DIM}{ANSI_PURPLE}'
CYAN = f'{RESET}{DIM}{ANSI_CYAN}'
WHITE = f'{RESET}{DIM}{ANSI_WHITE}'

BLACK2 = f'{RESET}{BOLD}{ANSI_BLACK}'
RED2 = f'{RESET}{BOLD}{ANSI_RED}'
GREEN2 = f'{RESET}{BOLD}{ANSI_GREEN}'
YELLOW2 = f'{RESET}{BOLD}{ANSI_YELLOW}'
BLUE2 = f'{RESET}{BOLD}{ANSI_BLUE}'
PURPLE2 = f'{RESET}{BOLD}{ANSI_PURPLE}'
CYAN2 = f'{RESET}{BOLD}{ANSI_CYAN}'
WHITE2 = f'{RESET}{BOLD}{ANSI_WHITE}'