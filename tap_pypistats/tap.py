"""Singer tap for PyPI Stats."""

from __future__ import annotations

__lazy_modules__ = {
    "datetime",
    "json",
    "pathlib",
    "requests",
    "requests.adapters",
    "requests_cache",
}

import argparse
import dataclasses
import datetime
import importlib.metadata
import json
import logging
import pathlib
import sys
from typing import IO, TYPE_CHECKING, Any

import requests
import requests.adapters
import requests_cache

if TYPE_CHECKING:
    from collections.abc import Generator, Iterable

BASE_URL = "https://pypistats.org/api"
VERSION = importlib.metadata.version("tap-pypistats")

DEFAULT_USER_AGENT = f"tap-pypistats/{VERSION}"

handler = logging.StreamHandler(sys.stderr)
handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))

logger = logging.getLogger(__name__)
logger.addHandler(handler)


@dataclasses.dataclass
class Config:
    """Configuration for the package."""

    packages: list[str]
    user_agent: str


class TapNamespace(argparse.Namespace):
    """A namespace for the tap command."""

    config: pathlib.Path

    def get_config(self: TapNamespace) -> Config:
        """Convert the namespace to a configuration."""
        with self.config.open(encoding="utf-8") as file:
            data = json.load(file)

            return Config(
                packages=data["packages"],
                user_agent=data.get("user_agent", DEFAULT_USER_AGENT),
            )


SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "properties": {
        "category": {"type": "string"},
        "date": {"type": "string", "format": "date"},
        "downloads": {"type": "integer"},
        "package": {"type": "string"},
    },
    "required": ["category", "date", "downloads"],
    "additionalProperties": False,
}


def write_message(message: dict[str, Any], *, stream: IO[str] = sys.stdout) -> None:
    """Write a message to a stream.

    :param dict message: The message to write.
    :param IO[str] stream: The stream to write to.
    """
    stream.write(json.dumps(message, default=str, separators=(",", ":")) + "\n")
    stream.flush()


def iter_python_minor(
    session: requests.Session,
    base_url: str,
    package_name: str,
    *,
    user_agent: str = DEFAULT_USER_AGENT,
) -> Generator[dict[str, Any], None, None]:
    """Iterate over the data for a package."""
    url = f"{base_url}/packages/{package_name}/python_minor"
    response = session.get(url, timeout=60, headers={"User-Agent": user_agent})
    response.raise_for_status()
    data = response.json()
    yield from data["data"]


def iter_system(
    session: requests.Session,
    base_url: str,
    package_name: str,
) -> Generator[dict[str, Any], None, None]:
    """Iterate over the data for a package."""
    url = f"{base_url}/packages/{package_name}/system"
    response = session.get(url, timeout=60)
    response.raise_for_status()
    data = response.json()
    yield from data["data"]


def iter_packages(
    base_url: str,
    packages: Iterable[str],
    *,
    user_agent: str = DEFAULT_USER_AGENT,
) -> Generator[dict[str, Any], None, None]:
    """Iterate over the data for a list of packages.

    :param str base_url: The base URL for the API.
    :param Iterable[str] packages: The names of the packages.
    :param str user_agent: The user agent to make requests
    :rtype: Iterator[dict]
    """
    now = datetime.datetime.now(datetime.UTC).isoformat()
    session = requests.Session()
    session.mount("https://", requests.adapters.HTTPAdapter(max_retries=5))

    yield {
        "type": "SCHEMA",
        "stream": "python_minor",
        "schema": SCHEMA,
        "key_properties": ["category", "date", "package"],
    }
    for package in packages:
        for record in iter_python_minor(session, base_url, package, user_agent=user_agent):
            yield {
                "type": "RECORD",
                "stream": "python_minor",
                "record": {
                    "package": package,
                    **record,
                },
                "time_extracted": now,
            }

    yield {
        "type": "SCHEMA",
        "stream": "system",
        "schema": SCHEMA,
        "key_properties": ["category", "date", "package"],
    }
    for package in packages:
        for record in iter_system(session, base_url, package):
            yield {
                "type": "RECORD",
                "stream": "system",
                "record": {
                    "package": package,
                    **record,
                },
                "time_extracted": now,
            }


def sync_packages(
    base_url: str,
    packages: Iterable[str],
    *,
    cache_name: str = "pypistats",
    stream: IO[str] = sys.stdout,
    user_agent: str = DEFAULT_USER_AGENT,
) -> None:
    """Sync data for a list of packages.

    :param str base_url: The base URL for the API.
    :param Iterable[str] packages: The names of the packages.
    :param str cache_name: The name of the cache.
    :param IO[str] stream: The stream to write to.
    :param str user_agent: The user agent to make requests with.
    :rtype: Iterator[dict]
    """
    requests_cache.install_cache(cache_name)
    for message in iter_packages(base_url, packages, user_agent=user_agent):
        write_message(message, stream=stream)


def main() -> None:
    """Run the main program."""
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument(
        "-c",
        "--config",
        help="path to the configuration file",
        required=True,
        type=pathlib.Path,
    )
    args = parser.parse_args(namespace=TapNamespace())

    try:
        config = args.get_config()
    except json.JSONDecodeError as error:
        logger.error("Configuration file is not valid JSON: %s", error)  # noqa: TRY400
        sys.exit(1)
    except FileNotFoundError as error:
        logger.error("Configuration file not found: %s", error)  # noqa: TRY400
        sys.exit(1)
    except Exception as error:  # noqa: BLE001
        logger.error("Error reading configuration: %s", error)  # noqa: TRY400
        sys.exit(1)

    sync_packages(
        BASE_URL,
        config.packages,
        stream=sys.stdout,
        user_agent=config.user_agent,
    )


if __name__ == "__main__":
    main()
