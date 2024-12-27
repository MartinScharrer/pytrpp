from pathlib import Path
from setuptools import setup

setup(
    name='pytrpp',
    version='0.3.2',
    description='Download TradeRepublic files and convert data for import in Portfolio Performance.',
    long_description=(Path(__file__).parent.resolve() / 'README.md').read_text('utf-8'),
    long_description_content_type='text/markdown',
    url='https://github.com/martinscharrer/pytrpp/',
    author='Martin Scharrer',
    author_email='martin.scharrer@web.de',
    license='MIT',
    packages=['pytrpp'],
    python_requires='>=3.12',
    entry_points={
        'console_scripts': [
            'pytrpp = pytrpp.main:main',
        ],
    },
    install_requires=[
        'certifi',
        'coloredlogs',
        'ecdsa',
        'packaging',
        'pathvalidate',
        'pygments',
        'requests_futures',
        'shtab',
        'websockets>=10.1',
    ],
    classifiers=[
        "License :: OSI Approved :: MIT License",
        'Programming Language :: Python :: 3 :: Only',
        "Operating System :: OS Independent",
        'Development Status :: 4 - Beta',
        "Topic :: Office/Business :: Financial",
        "Topic :: Office/Business :: Financial :: Investment",
    ],
    zip_safe=True,
)
