class MxEasySwitchError(Exception):
    """Base class for errors that should be shown without a traceback."""

    exit_code = 1


class ConfigurationError(MxEasySwitchError):
    exit_code = 2


class DependencyError(MxEasySwitchError):
    exit_code = 3


class DeviceUnavailableError(MxEasySwitchError):
    exit_code = 4


class DesktopIntegrationError(MxEasySwitchError):
    exit_code = 5
