from setuptools import setup, find_packages

setup(
    name='imageinn',
    version='0.1',
    packages=find_packages(),
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
        ],
    },
)
