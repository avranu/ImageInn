"""*********************************************************************************************************************
*                                                                                                                      *
*                                                                                                                      *
*                                                                                                                      *
*                                                                                                                      *
* -------------------------------------------------------------------------------------------------------------------- *
*                                                                                                                      *
*    METADATA:                                                                                                         *
*                                                                                                                      *
*        File:    test_fm.py                                                                                           *
*        Project: imageinn                                                                                             *
*        Version: 0.1.0                                                                                                *
*        Created: 2024-11-04                                                                                           *
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
import os
import time
from pathlib import Path
from typing import Iterator
class TestFm:
    def should_ignore_directory(self, directory: Path | str, *, allow_hidden : bool = False) -> bool:
        """
        Check if a directory should be ignored based on the name.

        Args:
            directory (Path): The directory to check.
            allow_hidden (bool): Whether to include hidden directories.

        Returns:
            bool: True if the directory should be ignored, False otherwise
        """
        directory = Path(directory)
    
        if not allow_hidden and (directory.name.startswith('.') or directory.name.startswith('__')):
            print("Ignoring hidden directory: %s", directory)
            return True

        return False

    def should_ignore_file(self, file_path: Path, *, allow_hidden : bool = True, **kwargs) -> bool:
        """
        Check if a file should be ignored based on the name.

        Implemented as a blacklist. 
        Superclasses should implement custom logic and then return super().should_ignore_file().

        Args:
            file_path: The file to check.
            allow_hidden: Whether to include hidden files.
            **kwargs: Additional arguments that subclasses may use.

        Returns:
            True if the file should be ignored, False otherwise.
        """
        if not allow_hidden and file_path.name.startswith('.'):
            return True

        return False

    def yield_directories(self, directory: Path, *, recursive: bool = True, allow_hidden : bool = False) -> Iterator[Path]:
        """
        Yield directories

        Args:
            directory (Path): The directory to search.
            recursive (bool): Whether to search recursively.
            allow_hidden (bool): Whether to include hidden directories.

        Yields:

        """
        if not recursive:
            if not self.should_ignore_directory(directory, allow_hidden=allow_hidden):
                yield directory
            return

        print('Searching %s for directories.', directory.absolute())

        for dirpath, dirnames, _ in os.walk(directory):
            dirpath_obj = Path(dirpath)
            
            # Skip hidden directories if not allowed
            if self.should_ignore_directory(dirpath_obj, allow_hidden=allow_hidden):
                continue
            
            # Skip ignored directories
            print('Dirnames before pruning WAS:', dirnames)
            dirnames[:] = [d for d in dirnames if not self.should_ignore_directory(d, allow_hidden=allow_hidden)]
            print('Dirnames after pruning IS:', dirnames)

            print(f'waiting to yield {dirpath_obj}')
            time.sleep(5)
            yield dirpath_obj

if __name__ == "__main__":
    test_fm = TestFm()
    test_path = Path(__file__).resolve().parents[2]
    count = 0  
    for directory in test_fm.yield_directories(Path.home()):
        count += 1
        print(directory)
        if count > 10:
            break
    print('Done.')