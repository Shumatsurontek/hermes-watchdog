"""Opt-in setup using Hermes's own CLI; preserve unrelated profile configuration."""

import argparse
import json
import os
import subprocess
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile-home", type=Path, help="Defaults to HERMES_HOME or ~/.hermes")
    args = parser.parse_args()
    profile = (args.profile_home or Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes")).expanduser().resolve()
    if not (profile / "plugins/hermes-watchdog/plugin.yaml").is_file():
        raise SystemExit(f"Install hermes-watchdog in {profile} first.")
    env = dict(os.environ, HERMES_HOME=str(profile))

    def hermes(*command, capture=False):
        return subprocess.run(
            ["hermes", *command],
            env=env,
            check=True,
            text=True,
            stdout=subprocess.PIPE if capture else None,
            timeout=60,
        ).stdout

    isolation = json.loads(hermes("config", "get", "plugins.isolation", "--json", capture=True))
    if isolation not in (None, "in_process"):
        raise SystemExit("Watchdog needs in-process plugins. Your isolation setting was not changed.")
    print(f"Configuring Watchdog in {profile}", flush=True)
    hermes("plugins", "enable", "hermes-watchdog")
    hermes("config", "set", "plugins.entries.hermes-watchdog.allow_gateway_injection", "true")
    # Desktop uses the CLI tool selection. Materialize the existing selection
    # before adding search, which is a valid lifecycle alias absent from the CLI selector.
    hermes("tools", "enable", "watchdog", "--platform", "cli")
    toolsets = json.loads(hermes("config", "get", "platform_toolsets.cli", "--json", capture=True))
    if not isinstance(toolsets, list) or len(toolsets) > 128 or not all(isinstance(x, str) for x in toolsets):
        raise SystemExit("Unexpected parent tool configuration; search was not added.")
    if "search" not in toolsets:
        hermes("config", "set", "platform_toolsets.cli", json.dumps(toolsets + ["search"]))
    print("Reopen Hermes Desktop, enable Watchdog in Capabilities → Plugins, and start a new conversation.")


if __name__ == "__main__":
    main()
