"""*********************************************************************************************************************
*                                                                                                                      *
*                                                                                                                      *
*                                                                                                                      *
*                                                                                                                      *
* -------------------------------------------------------------------------------------------------------------------- *
*                                                                                                                      *
*    METADATA:                                                                                                         *
*                                                                                                                      *
*        File:    exceptions.py                                                                                        *
*        Project: imageinn                                                                                             *
*        Version: 0.1.0                                                                                                *
*        Created: 2024-09-25                                                                                           *
*        Author:  Jess Mann                                                                                            *
*        Email:   jess.a.mann@gmail.com                                                                                *
*        Copyright (c) 2024 Jess Mann                                                                                  *
*                                                                                                                      *
* -------------------------------------------------------------------------------------------------------------------- *
*                                                                                                                      *
*    LAST MODIFIED:                                                                                                    *
*                                                                                                                      *
*        2024-12-12     By Jess Mann                                                                                   *
*                                                                                                                      *
*********************************************************************************************************************"""
class AppError(Exception):
	pass

class ShouldTerminateError(AppError):
	pass

class TooFastError(AppError):
	pass

class ChecksumMismatchError(AppError):
	pass

class UnexpectedStateError(AppError, RuntimeError):
    """
    The application has reached an unexpected state.
    """