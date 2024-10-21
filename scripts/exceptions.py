class AppException(Exception):
	pass


class ShouldTerminateException(AppException):
	pass


class TooFastException(AppException):
	pass
