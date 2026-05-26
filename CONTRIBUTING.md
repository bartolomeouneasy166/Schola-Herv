# Contributing to Schola-herv

Thank you for your interest in contributing! 🎉

## How to Contribute

1. **Fork** the repository and create your branch from `main`.
2. **Open an issue** first for significant changes so we can discuss the approach.
3. **Write clear commit messages** describing what and why.
4. **Add tests** for new functionality where possible.
5. **Submit a pull request** with a clear description of the change.

## Development Setup

```bash
git clone https://github.com/yahiashawon/schola-herv.git
cd schola-herv

# Option A – pip (editable install)
pip install -e ".[dev]"

# Option B – conda
conda env create -f environment.yml
conda activate schola_herv
pip install -e .
```

## Code Style

- Follow **PEP 8**.
- Use **type hints** for all public functions.
- Keep async code consistent — use `aiohttp` for HTTP, `asyncio` for concurrency.
- Document new public functions/classes with a docstring.

## Adding a New Search Source

1. Create `schola_herv/discovery/mysource.py` subclassing `BaseSearcher`.
2. Implement the `search(...)` async method.
3. Register it in `schola_herv/harvester.py` and `schola_herv/cli.py`.
4. Add it to the `--sources` choices in the CLI argument parser.

## Reporting Bugs

Please open a GitHub Issue and include:
- Python version and OS
- The command you ran
- The full error traceback

## License

By contributing, you agree your contributions will be licensed under the [MIT License](LICENSE).
