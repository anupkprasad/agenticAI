from setuptools import setup, find_packages

setup(
    name="agentic",
    version="0.0.0",
    packages=find_packages(exclude=("tests", "docs")),
    description="Minimal agentic AI scaffold for MD workflows",
)
