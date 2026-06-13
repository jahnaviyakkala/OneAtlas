# Contributing to OneAtlas AppSpec Engine

Thank you for your interest in contributing! This guide explains how to participate in the project.

## Getting Started

1. Fork the repository
2. Clone your fork: `git clone https://github.com/YOUR_USERNAME/oneatlas.git`
3. Create a feature branch: `git checkout -b feature/your-feature-name`
4. Make your changes and commit them
5. Push to your fork and submit a pull request

## Development Setup

```bash
# Install dependencies
uv sync

# Activate the virtual environment
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Run tests
pytest

# Run the development server
uv run uvicorn compiler.main:app --reload
```

## Code Style

- Follow PEP 8 guidelines
- Use type hints for all functions
- Add docstrings to public functions and classes
- Keep functions focused and under 50 lines when possible

## Reporting Issues

When reporting bugs, please include:
- Clear description of the issue
- Steps to reproduce
- Expected vs actual behavior
- Your environment (OS, Python version, etc.)

## Feature Requests

Feature requests are welcome! Please include:
- Clear use case and benefit
- Any relevant examples or context
- Implementation ideas (optional)

## Pull Request Process

1. Ensure tests pass locally
2. Update documentation if needed
3. Add a clear PR title and description
4. Link related issues using `#issue_number`
5. Wait for review and address feedback

## Questions?

Open a discussion or issue if you have questions about contributing.

---

**Happy coding! 🚀**
