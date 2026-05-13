## Summary

<!-- Briefly describe what this PR changes and why. -->

## Scope

- [ ] This change matches the requested task scope.
- [ ] This change does not introduce deferred technologies or unrelated features.
- [ ] This change does not modify unrelated files.

## Changed Files

<!-- List the main files or modules changed. -->

## Test Plan

<!-- List commands run and their results. If a command was not run, explain why. -->

- [ ] `pytest`
- [ ] `ruff check .`
- [ ] `mypy .`

## Security Checklist

- [ ] No real credentials, tokens, private keys, production IPs, or production topology data are included.
- [ ] No secrets are logged or exposed in error messages.
- [ ] External network operations have explicit timeouts where applicable.
- [ ] Neo4j queries use parameterized Cypher where applicable.
- [ ] SSH-related changes only allow read-only commands where applicable.

## Compatibility

- [ ] Compatible with Python 3.11.
- [ ] No Python 3.12+ only language features or standard-library APIs were introduced.

## Documentation

- [ ] Public documentation was updated if behavior, configuration, or architecture changed.
- [ ] No local-only agent rules or private workflow notes are referenced by public documentation.

## Reviewer Notes

<!-- Add anything reviewers should pay special attention to. -->
