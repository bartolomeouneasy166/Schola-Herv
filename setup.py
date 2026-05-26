"""
Fallback setup.py for editable installs with older pip versions.
The canonical packaging metadata lives in pyproject.toml.
"""

from setuptools import setup, find_packages

setup(
    name="schola-herv",
    version="2.0.0",
    description="Mass-scale academic paper discovery and PDF harvesting for LLM corpus building.",
    long_description=open("README.md", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    author="Yahia Shawon",
    author_email="yahiashawon@ihep.ac.cn",
    url="https://github.com/yahiashawon/schola-herv",
    license="MIT",
    python_requires=">=3.10",
    packages=find_packages(exclude=["tests*"]),
    package_data={"schola_herv": ["recipes/*.yaml"]},
    install_requires=[
        "rich>=13.0.0",
        "pyyaml>=6.0",
        "aiohttp>=3.9.0",
        "arxiv>=2.1.0",
        "biopython>=1.83",
        "habanero>=1.2.0",
        "pymupdf>=1.23.0",
        "tenacity>=8.2.0",
        "tqdm>=4.66.0",
        "flask>=3.0.0",
        "openpyxl>=3.1.0",
        "beautifulsoup4>=4.12.0",
    ],
    entry_points={
        "console_scripts": [
            "schola-herv = schola_herv.cli:main",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "Topic :: Scientific/Engineering :: Information Analysis",
    ],
    keywords="academic papers pdf download arxiv pubmed openalex nlp corpus llm research",
)
