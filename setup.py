from setuptools import setup, find_packages

setup(
    name="thermal_analyzer",
    version="0.2.0",
    description="A Python package for analyzing thermal test data from Excel sheets.",
    author="Your Name",
    packages=find_packages(),
    install_requires=[
        "pandas>=1.5.0",
        "numpy>=1.20.0",
        "matplotlib>=3.5.0",
        "openpyxl>=3.0.0",
        "xlsxwriter>=3.0.0",
        "jinja2>=3.0.0",
    ],
    entry_points={
        "console_scripts": [
            "thermal=thermal_analyzer.ui.cli:main",
        ],
    },
    python_requires=">=3.10",
)
