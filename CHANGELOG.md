# Changelog

All notable changes to the OneAtlas AppSpec Engine project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Comprehensive project documentation (Architecture, Setup guides)
- EditorConfig for consistent code formatting across editors
- GitHub Actions CI/CD pipeline for automated testing and linting
- MIT License for open-source distribution
- Enhanced .gitignore for better file management
- Detailed CONTRIBUTING guidelines for project contributors

### Changed
- Improved boot.py with better documentation and error handling
- Enhanced environment setup with comprehensive guides

### Fixed
- Bootstrap script now handles missing frontend generation gracefully

## [1.0.0] - 2026-06-13

### Added
- Initial release of OneAtlas AppSpec Engine
- Multi-stage AI compilation pipeline
- Self-repair engine with 3-tier repair loop
- Human-in-the-Loop (HITL) capabilities
- Integration registry with predefined stubs
- FastAPI backend with CrewAI orchestration
- React + Vite frontend
- Docker support
- Groq/Gemini/OpenRouter provider routing
- Comprehensive evaluation framework
- Mermaid diagram generation

### Features in v1.0.0
- 100% success rate on evaluated prompts
- ~195 seconds average generation time
- ~$0.02 average cost per run
- 2.5 average repair attempts per prompt
- Support for 6 major integrations
- 4 additional integration stubs

---

## Guidelines

- Use semantic versioning (MAJOR.MINOR.PATCH)
- Document breaking changes clearly
- Link to relevant issues using #issue_number
- Group changes by type: Added, Changed, Fixed, Deprecated, Removed, Security

## Future Roadmap

- [ ] Streaming responses for real-time generation feedback
- [ ] Advanced caching for repeated prompts
- [ ] Custom integration builder UI
- [ ] Analytics dashboard for pipeline metrics
- [ ] Multi-language support (currently English-only)
- [ ] GraphQL API alternative
- [ ] Webhook support for external integrations
