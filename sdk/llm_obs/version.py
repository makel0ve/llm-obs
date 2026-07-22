from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as metadata_version


PACKAGE_NAME = "llm-obs-sdk"
UNKNOWN_VERSION = "0.0.0+unknown"


def get_version() -> str:
    try:
        return metadata_version(PACKAGE_NAME)
    except PackageNotFoundError:
        return UNKNOWN_VERSION


__version__ = get_version()


def user_agent() -> str:
    return f"{PACKAGE_NAME}/{get_version()}"
