from pathlib import Path

from tap_pypistats.tap import DEFAULT_USER_AGENT, Config, TapNamespace


def test_tap_namespace_get_config(tmp_path: Path) -> None:
    """It should convert a namespace to a config."""
    config = tmp_path / "config.json"
    config.write_text('{"packages": ["foo", "bar"]}')

    namespace = TapNamespace(config=config)

    assert namespace.get_config() == Config(
        packages=["foo", "bar"],
        user_agent=DEFAULT_USER_AGENT,
    )
