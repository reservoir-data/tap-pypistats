from __future__ import annotations

import typing as t

from tap_pypistats.tap import iter_packages

if t.TYPE_CHECKING:
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


def test_iter_packages(httpserver: HTTPServer):
    package_name = "package_name"
    base_url = httpserver.url_for("").strip("/")
    system = f"/packages/{package_name}/system"
    python_minor = f"/packages/{package_name}/python_minor"

    httpserver.expect_oneshot_request(system).respond_with_data(EXAMPLE_SYSTEM_RESPONSE)
    httpserver.expect_oneshot_request(python_minor).respond_with_data(EXAMPLE_PYTHON_MINOR_RESPONSE)

    messages = list(iter_packages(base_url, [package_name]))
    assert len(messages) == 1 + 5 + 1 + 9
