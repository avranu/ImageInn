"""*********************************************************************************************************************
*                                                                                                                      *
*                                                                                                                      *
*                                                                                                                      *
*                                                                                                                      *
* -------------------------------------------------------------------------------------------------------------------- *
*                                                                                                                      *
*    METADATA:                                                                                                         *
*                                                                                                                      *
*        File:    script.py                                                                                            *
*        Project: imageinn                                                                                             *
*        Version: 0.1.0                                                                                                *
*        Created: 2024-10-09                                                                                           *
*        Author:  Jess Mann                                                                                            *
*        Email:   jess.a.mann@gmail.com                                                                                *
*        Copyright (c) 2025 Jess Mann                                                                                  *
*                                                                                                                      *
* -------------------------------------------------------------------------------------------------------------------- *
*                                                                                                                      *
*    LAST MODIFIED:                                                                                                    *
*                                                                                                                      *
*        2024-11-04     By Jess Mann                                                                                   *
*                                                                                                                      *
*********************************************************************************************************************"""
from __future__ import annotations
from abc import ABC
import os
import subprocess
import shutil
import logging
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator
from alive_progress import alive_it, alive_bar
from scripts.lib.types import ProgressBar

logger = logging.getLogger(__name__)

class Script(BaseModel, ABC):

    max_threads : int = 0
    _progress_bar : ProgressBar | None = PrivateAttr(default=None)
    _progress_message : str | None = PrivateAttr(default=None)

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @property
    def progress_bar(self) -> ProgressBar:
        if not self._progress_bar:
            self._progress_bar = alive_bar(title="Running", unknown='waves')
        return self._progress_bar

    @field_validator("max_threads", mode="before")
    def validate_max_threads(cls, value):
        # Sensible default
        if not value:
            # default is between 1-4 threads. More than 4 presumptively stresses the HDD non-optimally.
            return max(1, min(4, round(os.cpu_count() / 2)))
            
        if value < 1:
            raise ValueError("max_threads must be a positive integer.")

        return value

    @classmethod
    def subprocess(cls, command : list[str] | str, **kwargs) -> subprocess.CompletedProcess:
        # default check=True
        if 'check' not in kwargs:
            kwargs['check'] = True

        # default timeout=60
        if 'timeout' not in kwargs:
            kwargs['timeout'] = 60

        if isinstance(command, str):
            command = command.split()

        try:
            return subprocess.run(command, **kwargs)
        except FileNotFoundError as e:
            logger.debug("Command '%s' not found. Trying to locate it with shutil.", command)

            # Try to locate the command with shutil
            if not (exe := shutil.which(command[0])):
                raise FileNotFoundError(f"Command '{command[0]}' not found.") from e

        command[0] = exe
        return subprocess.run(command, **kwargs)


    @classmethod
    def get_network_gateway(cls) -> str:
        """
        Retrieves the default gateway IP address on WSL.
        """
        try:
            result = cls.subprocess(
                ['ip', 'route', 'show', 'default'],
                capture_output=True, text=True
            )
            gateway_ip = result.stdout.split()[2]
            logger.info(f"Detected gateway IP: {gateway_ip}")
            return gateway_ip
        except (subprocess.CalledProcessError, IndexError) as e:
            logger.error("Error getting the default gateway IP.")
            logger.debug(e)
            return ""


    @classmethod
    def get_network_ssid(cls) -> str:
        """
        Retrieves the SSID of the current network.
        """
        # If not on Windows, return an empty string
        if os.name != 'nt' or not shutil.which('powershell.exe'):
            return ""
        
        try:
            result = cls.subprocess(
                ['powershell.exe', 'netsh wlan show interfaces'],
                capture_output=True, text=True
            )
            for line in result.stdout.splitlines():
                if "SSID" in line and "BSSID" not in line:
                    ssid = line.split(":")[1].strip()
                    logger.debug(f"Detected SSID: {ssid}")
                    return ssid
        except subprocess.CalledProcessError as e:
            logger.error("Error retrieving the current SSID.")
            logger.debug(e)
            return ""


    @classmethod
    def is_home_network(cls) -> bool:
        """
        Determines if the current network is the home network.
        """
        if not (home_network_name := os.getenv("IMAGEINN_HOME_NETWORK")):
            logger.error("Home network name not set. Set the IMAGEINN_HOME_NETWORK environment variable.")
            return False
        
        return cls.get_network_ssid().lower() == home_network_name.lower()

    def progress_message(self, message: str | None = None, *args, max_length : int = 30, advance : int = 0) -> None:
        """
        Update the progress bar with a message.

        Args:
            message (str): The message to display.
            *args: Additional arguments to format the message.
            max_length (int): The maximum length of the message to display. Default 30.
            advance (int): The number of steps to advance the progress bar.
        """
        if message:
            # Combine message and args into a single string, ensuring message isn't truncated, but args are
            message_length = len(message)
            arg_text = ' '.join([str(arg).strip() for arg in args])
            arg_start_index = -1 * (max_length - message_length - 1)
            if len(arg_text) > max_length - message_length - 1:
                arg_text = f'...{arg_text[arg_start_index:]}'
            text = f'{message} {arg_text}'
            self._progress_message = text.strip()
            logger.debug('New progress bar message: %s', self._progress_message)
            
        self.progress_bar.text(self.report(self._progress_message))
        
        if advance:
            self.progress_bar(advance)

    def progress_advance(self, message_prefix : str | None = None, advance : int = 1):
        """
        Report progress to the progress bar.

        Args:
            message_prefix: An optional message to prefix the report with.
        """
        self.progress_message(message_prefix, advance=advance)

    def report(self, message_prefix : str | None = None) -> str:
        """
        Create a report of the process so far.

        Args:
            message_prefix: An optional message to prefix the report with.

        Returns:
            The report string.
        """
        raise NotImplementedError(f"Subclass {self.__class__.__name__} does not implement 'report' method.")