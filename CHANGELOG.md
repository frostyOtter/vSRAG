# Changelog

## [Unreleased]

### Changed

- Validate and resolve business folders through a FastAPI dependency before answering requests.
- Pass the validated business path to the answer service instead of resolving it again.
