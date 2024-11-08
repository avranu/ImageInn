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
*        Copyright (c) 2024 Jess Mann                                                                                  *
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

logger = logging.getLogger(__name__)

class Script(BaseModel, ABC):

    model_config = ConfigDict(arbitrary_types_allowed=True)

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