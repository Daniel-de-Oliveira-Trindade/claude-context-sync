from setuptools import setup, find_packages

setup(
    name="claude-context-sync",
    version="0.5.0",
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        "click>=8.1.0",
        "jsonschema>=4.17.0",
        "tqdm>=4.65.0",
        "cryptography>=41.0.0",
    ],
    entry_points={
        "console_scripts": [
            "claude-sync=claude_context_sync.main:main",
        ],
    },
    author="Claude Session Sync Team",
    description="Transfer Claude Code context (sessions, file history, todos) between devices",
    python_requires=">=3.8",
)