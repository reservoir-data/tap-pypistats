"""Singer tap for PyPI Stats."""

from __future__ import annotations

__lazy_modules__ = {"datetime", "http", "json", "pathlib", "urllib3"}

import argparse
import dataclasses
import datetime as dt
import http
import importlib.metadata
import json
import logging
import pathlib
import sys
from typing import IO, TYPE_CHECKING, Any

import urllib3

if TYPE_CHECKING:
    from collections.abc import Generator

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
    client: urllib3.PoolManager,
    base_url: str,
    package_name: str,
) -> Generator[dict[str, Any]]:
    """Iterate over the data for a package."""
    url = f"{base_url}/packages/{package_name}/python_minor"
    response = client.request(http.HTTPMethod.GET, url)
    if response.status != http.HTTPStatus.OK:
        msg = f"Request failed: {response.reason or 'Unknown reason'}"
        raise RuntimeError(msg)
    data = response.json()
    yield from data["data"]


def iter_system(
    client: urllib3.PoolManager,
    base_url: str,
    package_name: str,
) -> Generator[dict[str, Any]]:
    """Iterate over the data for a package."""
    url = f"{base_url}/packages/{package_name}/system"
    response = client.request(http.HTTPMethod.GET, url)
    if response.status != http.HTTPStatus.OK:
        msg = f"Request failed: {response.reason or 'Unknown reason'}"
        raise RuntimeError(msg)
    data = response.json()
    yield from data["data"]


def iter_packages(
    base_url: str,
    packages: list[str],
    *,
    user_agent: str = DEFAULT_USER_AGENT,
    retries: urllib3.Retry | None = None,
) -> Generator[dict[str, Any]]:
    """Iterate over the data for a list of packages.

    :param str base_url: The base URL for the API.
    :param list[str] packages: The names of the packages.
    :param str user_agent: The user agent to make requests
    :param urllib3.Retry retries: Optional retry configuration, defaults to ``get_retries``.
    :rtype: Iterator[dict]
    """
    now = dt.datetime.now(dt.UTC).isoformat()
    retries = retries if retries is not None else get_retries()
    client = urllib3.PoolManager(
        num_pools=len(packages),
        timeout=60,
        headers={"User-Agent": user_agent},
        retries=retries,
    )

    yield {
        "type": "SCHEMA",
        "stream": "python_minor",
        "schema": SCHEMA,
        "key_properties": ["category", "date", "package"],
    }
    for package in packages:
        for record in iter_python_minor(client, base_url, package):
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
        for record in iter_system(client, base_url, package):
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
    packages: list[str],
    *,
    stream: IO[str] = sys.stdout,
    user_agent: str = DEFAULT_USER_AGENT,
    retries: urllib3.Retry | None = None,
) -> None:
    """Sync data for a list of packages.

    :param str base_url: The base URL for the API.
    :param list[str] packages: The names of the packages.
    :param str cache_name: The name of the cache.
    :param IO[str] stream: The stream to write to.
    :param str user_agent: The user agent to make requests with.
    :param urllib3.Retry retries: Optional retry configuration, defaults to ``get_retries``.
    :rtype: Iterator[dict]
    """
    for message in iter_packages(base_url, packages, user_agent=user_agent, retries=retries):
        write_message(message, stream=stream)


def get_retries(
    *,
    total: int = 5,
    backoff_factor: int = 1,
) -> urllib3.Retry:
    """Get the request retrying configuration.

    :param int total: Total number of retries to allow.
    :param int backoff_factor: A backoff factor to apply between attempts after the second try.
    :rtype: urllib3.Retry
    """
    return urllib3.Retry(
        total=total,
        backoff_factor=backoff_factor,
        status_forcelist=[429, 500, 502, 503, 504],
        respect_retry_after_header=True,
        raise_on_status=False,
    )


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
        logger.error("Configuration file is not valid JSON: %s", error)  # ruff: ignore[error-instead-of-exception]
        sys.exit(1)
    except FileNotFoundError as error:
        logger.error("Configuration file not found: %s", error)  # ruff: ignore[error-instead-of-exception]
        sys.exit(1)
    except Exception as error:  # ruff: ignore[blind-except]
        logger.error("Error reading configuration: %s", error)  # ruff: ignore[error-instead-of-exception]
        sys.exit(1)

    sync_packages(
        BASE_URL,
        config.packages,
        stream=sys.stdout,
        user_agent=config.user_agent,
    )


if __name__ == "__main__":
    main()
