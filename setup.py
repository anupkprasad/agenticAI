"""
setup.py — Package configuration for the `agentic` library.

This file defines the build and distribution metadata for the agentic AI
scaffold project. It uses setuptools to discover all sub-packages automatically
(excluding test and documentation directories) so the package can be installed
locally with `pip install -e .` or published to PyPI.

Package: agentic
Purpose: Minimal agentic AI scaffold designed for MD (Medical/Markdown) workflows.
         Provides a lightweight foundation for building, extending, and running
         AI-powered agents within structured workflow pipelines.
"""
from setuptools import setup, find_packages

setup(
    name="agentic",
    version="0.0.0",
    packages=find_packages(exclude=("tests", "docs")),
    description="Minimal agentic AI scaffold for MD workflows",
)
