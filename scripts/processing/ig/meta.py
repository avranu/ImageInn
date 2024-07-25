from enum import Enum
import logging
import os
from pathlib import Path
import platform
from scripts.lib.types import Number

logger = logging.getLogger(__name__)

DEFAULT_CANVAS_SIZE : int = 2160
DEFAULT_MARGIN : int = 100
DEFAULT_BLUR : int = 100
DEFAULT_BRIGHTNESS : Number = 1.8
DEFAULT_CONTRAST : Number = 0.5
DEFAULT_SATURATION : Number = 0.5
DEFAULT_BORDER : int = 8

class AdjustmentTypes(Enum):
    BASIC = 'basic-adjustments'
    COLOR = 'color'
    BRIGHTNESS = 'brightness'
    CONTRAST = 'contrast'
    TOPAZ = 'topaz'

def get_topaz_path() -> Path | None:
    if platform.system() == 'Linux' and ('Microsoft' in platform.release() or os.name == 'posix'):
        logger.info('Detected platform: WSL')
        return Path("/mnt/c/Program Files/Topaz Labs LLC/Topaz Photo AI/tpai.exe")

    if platform.system() == 'Linux':
        logger.info('Detected platform: Linux')
        return Path("/mnt/c/Program Files/Topaz Labs LLC/Topaz Photo AI/tpai.exe")
        
    if platform.system() == 'Windows':
        logger.info('Detected platform: Windows')
        return Path(r"C:/Program Files/Topaz Labs LLC/Topaz Photo AI/tpai.exe")

    if platform.system() == 'Darwin':
        logger.info('Detected platform: macOS')
        return Path("/Applications/Topaz Labs LLC/Topaz Photo AI/tpai.app")

    logger.info('Unknown platform: %s', platform.system())
    return None

DEFAULT_TOPAZ_PATH = get_topaz_path()

def to_windows_path(path: Path) -> str:
    return str(path).replace('/mnt/c/', 'C:\\').replace('/', '\\')