"""Compatibility entry point for the CraftEye Streamlit site.

The web application lives in the ``website`` package so the project root stays
focused on data, models, packaging, and documentation.
"""
from website import app as _application  # noqa: F401
