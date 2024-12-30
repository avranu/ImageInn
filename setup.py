"""*********************************************************************************************************************
*                                                                                                                      *
*                                                                                                                      *
*                                                                                                                      *
*                                                                                                                      *
* -------------------------------------------------------------------------------------------------------------------- *
*                                                                                                                      *
*    METADATA:                                                                                                         *
*                                                                                                                      *
*        File:    setup.py                                                                                             *
*        Project: imageinn                                                                                             *
*        Version: 0.1.0                                                                                                *
*        Created: 2024-10-08                                                                                           *
*        Author:  Jess Mann                                                                                            *
*        Email:   jess.a.mann@gmail.com                                                                                *
*        Copyright (c) 2024 Jess Mann                                                                                  *
*                                                                                                                      *
* -------------------------------------------------------------------------------------------------------------------- *
*                                                                                                                      *
*    LAST MODIFIED:                                                                                                    *
*                                                                                                                      *
*        2024-12-29     By Jess Mann                                                                                   *
*                                                                                                                      *
*********************************************************************************************************************"""
from setuptools import setup, find_packages

setup(
    name='imageinn',
    version='0.1.2',
    packages=find_packages(),
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    author="Jess Mann",
    python_requires=">=3.10",
    install_requires=[
        'tqdm',
        'exifread',
        'djangofoundry',
        'argparse',
        'rawpy',
        'imageio',
        'colorlog',
        'pydantic',
        'xxhash',
        'cachetools',
        'python-dotenv',
    ],
    entry_points={
        'console_scripts': [
            'upload=scripts.thumbnails.upload.progressive:main',
            'organize=scripts.monthly.organize.base:main',
        ],
    },
)