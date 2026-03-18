#!/usr/bin/env bash
# codecks.sh — Wrapper script for codecks-cli
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" || -n "$WINDIR" ]]; then
  export PYTHONPATH="C:/Users/USER/GitHubDirectory/codecks-cli"
  exec "C:/Users/USER/GitHubDirectory/codecks-cli/.venv/Scripts/python" -m codecks_cli.cli "$@"
else
  export PYTHONPATH="/mnt/c/Users/USER/GitHubDirectory/codecks-cli"
  exec python3 -m codecks_cli.cli "$@"
fi
