from setuptools import setup, find_packages

setup(
    name="google-adk",
    version="0.0.1",
    packages=find_packages(include=["google", "google.*"]),
    include_package_data=True,
    entry_points={
        "console_scripts": [
            "adk=google.adk.cli:main",  # Make sure this points to your CLI entry point
        ],
    },
    install_requires=[],
)
