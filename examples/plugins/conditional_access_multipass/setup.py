from setuptools import find_packages, setup

setup(
    name="access-conditional-access",
    install_requires=["pluggy==1.4.0"],
    py_modules=["conditional_access"],
    packages=find_packages(),
    entry_points={
        "access_conditional_access": ["conditional_access = conditional_access"],
    },
)
