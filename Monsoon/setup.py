#!/usr/bin/env python3

from pathlib import Path

from setuptools import find_packages, setup

# Read the long description from README
here = Path(__file__).parent.resolve()
readme_path = here / "README"
if not readme_path.exists():
    readme_path = here / "README.md"

long_description = (
    readme_path.read_text(encoding="utf-8") if readme_path.exists() else ""
)

setup(
    name="Pymonsoon",
    version="0.1.0",
    description="Monsoon Power Monitor API",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://www.msoon.com/LabEquipment/PowerMonitor/",
    author="Michael Brinker",
    author_email="mikeb@msoon.com",
    license="MIT",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3 :: Only",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Hardware",
        "Topic :: Scientific/Engineering",
    ],
    keywords="power measurement monsoon hvpm pm",
    packages=find_packages(exclude=["build", "docs", "tests*"]),
    python_requires=">=3.8",
    install_requires=[
        "numpy>=1.20.0",
        "pyusb>=1.0.0",
    ],
)
