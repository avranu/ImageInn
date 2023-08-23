"""
	
	Metadata:
	
		File: provider.py
		Project: providers
		Created Date: 23 Aug 2023
		Author: Jess Mann
		Email: jess.a.mann@gmail.com
	
		-----
	
		Last Modified: Wed Aug 23 2023
		Modified By: Jess Mann
	
		-----
	
		Copyright (c) 2023 Jess Mann
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Union, Optional
import subprocess
import logging
from scripts.lib.path import FilePath, DirPath

logger = logging.getLogger(__name__)

class Provider(ABC):

	@abstractmethod
	def run(self, *args, **kwargs) -> Any:
		"""
		Initiate the provider process, running self.next() for each action that needs to occur. This method should be implemented in a subclass.
		
		Args:
			*args: Variable length argument list.
			**kwargs: Arbitrary keyword arguments.
			
		Returns:
			Any: returns a type defined by the subclass.
		"""
		# TODO multiple and single run methods
		raise NotImplementedError("Provider.run() must be implemented in a subclass.")
	
	@abstractmethod
	def next(self, *args, **kwargs) -> Any:
		"""
		Initiate the provider process for a single iteration. This method should be implemented in a subclass.
	
		Args:
			*args: Variable length argument list.
			**kwargs: Arbitrary keyword arguments.
			
		Returns:
			Any: returns a type defined by the subclass.
		"""
		raise NotImplementedError("Provider.next() must be implemented in a subclass.")
	
	def subprocess(self, command : Optional[list[str]] = None, cwd : Optional[DirPath | str] = None, check : bool = True, timeout : Optional[float] = None) -> tuple[str, str]:
		"""
		Run a subprocess, printing the command and output to the user.

		Args:
			command (str):
				The command to run.
			cwd (DirPath, optional):
				The working directory to run the command in. Defaults to None.
			check (bool, optional):
				Whether to raise an exception if the command fails. Defaults to True.

		Returns:
			tuple[str, str]: The output of the command, and the error str from the command.

		Raises:
			subprocess.CalledProcessError:
				If the command fails, and check is True.
				Otherwise, the error is logged, and the error message is returned when an exception is encountered.
		"""
		try:
			# Run the command
			output = subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=check, timeout=timeout)
		except subprocess.CalledProcessError as e:
			logger.error('Command failed: %s', command)
			logger.error('Error message: %s', e.stderr)
			logger.error('Output: %s', e.stdout)

			if check:
				raise e from e
			else:
				return getattr(output, 'stdout', ''), e.stderr

		if output.stdout:
			logger.debug(output.stdout)

		if output.stderr:
			logger.debug(output.stderr)

			if output.returncode != 0:
				logger.error('Command failed: %s', command)
				logger.error('Error message: %s', output.stderr)
				logger.error('Output: %s', output.stdout)
				if check:
					raise subprocess.CalledProcessError(output.returncode, command, output.stderr)

		# Return the output
		return output.stdout, output.stderr
