from setuptools import setup, find_packages
setup(
    name="sirius-code",
    version="1.0.0",
    description="Sirius Code — Agente autônomo de programação",
    packages=find_packages(),
    install_requires=["httpx>=0.27.0"],
    entry_points={"console_scripts": ["sirius=sirius_code.cli:main"]},
    python_requires=">=3.9",
)
