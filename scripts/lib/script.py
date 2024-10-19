from __future__ import annotations
from abc import ABC
import subprocess
import shutil
import logging
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator

logger = logging.getLogger(__name__)

class Script(BaseModel, ABC):
    
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    def subprocess(self, command : list[str] | str, **kwargs) -> subprocess.CompletedProcess:
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