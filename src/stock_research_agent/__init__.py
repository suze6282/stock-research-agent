"""Deterministic, offline package bootstrap."""

import os

# Third-party Pydantic plugins are deliberately unsupported. Plugin discovery
# scans installed distribution metadata during model construction, which would
# make imports environment-dependent and perform filesystem I/O. Force the
# disable-all policy before any application submodule can define a Pydantic
# model, overriding caller values that could still permit discovery.
os.environ["PYDANTIC_DISABLE_PLUGINS"] = "__all__"

__version__ = "0.1.0"
