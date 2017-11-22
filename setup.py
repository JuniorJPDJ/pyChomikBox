from setuptools import find_packages, setup
import os

about = {}
here = os.path.abspath(os.path.dirname(__file__))
with open(os.path.join(here, "ChomikBox", "__version__.py")) as f:
    exec(f.read(), about)

with open('README.rst') as f:
    long_description = f.read()

__version__ = about['__version__']
required = ['requests', 'requests_toolbelt', 'xmltodict']

setup(
    name='pyChomikBox',
    version=__version__,
    description='Python library for Chomikuj.pl filesharing service',
    long_description=long_description,
    author='JuniorJPDJ',
    author_email="juniorjpdj@interia.pl",
    url='https://github.com/JuniorJPDJ/pyChomikBox',
    packages=find_packages(exclude=['contrib', 'docs', 'tests', 'examples']),
    install_requires=required,
    license='LGPLv3+',
    python_requires='>=2.7, !=3.0.*, !=3.1.*, !=3.2.*, !=3.3.*, !=3.4.*, <4',
    keywords="chomikuj chomik file share sharing upload download uploader downloader",
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Topic :: Communications :: Chat',
        'License :: OSI Approved :: GNU Lesser General Public License v3 or later (LGPLv3+)',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3', 'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: Implementation :: CPython'
    ], )
