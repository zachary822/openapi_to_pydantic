from setuptools import find_packages, setup

setup(
    name="openapi_to_pydantic",
    version="0.0.1",
    author="Zachary Juang",
    author_email="zacharyjuang@gmail.com",
    packages=find_packages(),
    install_requires=[
        "pydantic",
        "black",
        "isort",
        "pyyaml",
        "autoflake",
    ],
)
