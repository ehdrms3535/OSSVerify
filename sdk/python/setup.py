from setuptools import find_packages, setup

setup(
    name="ossverify-client",
    version="1.0.0",
    description="OSSVerify Python SDK — open-source contribution intelligence client",
    packages=find_packages(),
    python_requires=">=3.9",
    install_requires=["requests>=2.28.0"],
)
