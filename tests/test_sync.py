from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tap_pypistats.tap import get_retries, iter_packages

if TYPE_CHECKING:
    from pytest_httpserver import HTTPServer

EXAMPLE_PYTHON_MINOR_RESPONSE = """
{
  "data": [
    {
      "category": "2.6",
      "date": "2018-02-08",
      "downloads": 1
    },
    {
      "category": "2.7",
      "date": "2018-02-08",
      "downloads": 1
    },
    {
      "category": "3.2",
      "date": "2018-02-08",
      "downloads": 1
    },
    {
      "category": "3.3",
      "date": "2018-02-08",
      "downloads": 1
    },
    {
      "category": "3.4",
      "date": "2018-02-08",
      "downloads": 1
    },
    {
      "category": "3.5",
      "date": "2018-02-08",
      "downloads": 1
    },
    {
      "category": "3.6",
      "date": "2018-02-08",
      "downloads": 1
    },
    {
      "category": "3.7",
      "date": "2018-02-08",
      "downloads": 1
    },
    {
      "category": "null",
      "date": "2018-02-08",
      "downloads": 1
    }
  ],
  "package": "package_name",
  "type": "python_minor_downloads"
}
"""

EXAMPLE_SYSTEM_RESPONSE = """
{
  "data": [
    {
      "category": "darwin",
      "date": "2018-02-08",
      "downloads": 1
    },
    {
      "category": "linux",
      "date": "2018-02-08",
      "downloads": 1
    },
    {
      "category": "null",
      "date": "2018-02-08",
      "downloads": 1
    },
    {
      "category": "other",
      "date": "2018-02-08",
      "downloads": 1
    },
    {
      "category": "windows",
      "date": "2018-02-08",
      "downloads": 1
    }
  ],
  "package": "package_name",
  "type": "system_downloads"
}
"""


def test_iter_packages(httpserver: HTTPServer) -> None:
    package_name = "package_name"
    base_url = httpserver.url_for("").strip("/")
    system = f"/packages/{package_name}/system"
    python_minor = f"/packages/{package_name}/python_minor"

    httpserver.expect_oneshot_request(system).respond_with_data(EXAMPLE_SYSTEM_RESPONSE)
    httpserver.expect_oneshot_request(python_minor).respond_with_data(EXAMPLE_PYTHON_MINOR_RESPONSE)

    messages = list(iter_packages(base_url, [package_name]))
    assert len(messages) == 1 + 5 + 1 + 9


def test_retry_after_on_rate_limit(httpserver: HTTPServer) -> None:
    """It should wait and retry when rate limited."""
    package_name = "package_name"
    base_url = httpserver.url_for("").strip("/")
    system = f"/packages/{package_name}/system"
    python_minor = f"/packages/{package_name}/python_minor"

    httpserver.expect_oneshot_request(python_minor).respond_with_data(
        "Too Many Requests",
        status=429,
        headers={"Retry-After": "1"},
    )
    httpserver.expect_oneshot_request(python_minor).respond_with_data(EXAMPLE_PYTHON_MINOR_RESPONSE)
    httpserver.expect_oneshot_request(system).respond_with_data(EXAMPLE_SYSTEM_RESPONSE)

    messages = list(iter_packages(base_url, [package_name]))
    assert len(messages) == 1 + 5 + 1 + 9
    httpserver.check_assertions()


def test_retry_server_error(httpserver: HTTPServer) -> None:
    """It should retry transient server errors."""
    package_name = "package_name"
    base_url = httpserver.url_for("").strip("/")
    system = f"/packages/{package_name}/system"
    python_minor = f"/packages/{package_name}/python_minor"

    httpserver.expect_oneshot_request(python_minor).respond_with_data("", status=503)
    httpserver.expect_oneshot_request(python_minor).respond_with_data(EXAMPLE_PYTHON_MINOR_RESPONSE)
    httpserver.expect_oneshot_request(system).respond_with_data(EXAMPLE_SYSTEM_RESPONSE)

    messages = list(iter_packages(base_url, [package_name], retries=get_retries(backoff_factor=0)))
    assert len(messages) == 1 + 5 + 1 + 9


def test_retries_exhausted(httpserver: HTTPServer) -> None:
    """It should raise after exhausting retries."""
    httpserver.expect_request("/packages/package_name/python_minor").respond_with_data(
        "",
        status=429,
    )

    with pytest.raises(RuntimeError, match="Request failed"):
        list(
            iter_packages(
                httpserver.url_for("").strip("/"),
                ["package_name"],
                retries=get_retries(total=2, backoff_factor=0),
            )
        )

    expected_requests = 3
    assert len(httpserver.log) == expected_requests  # initial request + 2 retries
