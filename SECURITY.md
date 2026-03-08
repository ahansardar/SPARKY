# Security Policy

## Supported Versions

SPARKY is currently maintained on the latest release line only. Security fixes are applied to the most recent stable version and may not be backported to older releases.

| Version | Supported |
| ------- | --------- |
| 1.1.x   | :white_check_mark: |
| 1.0.x   | :x: |
| < 1.0   | :x: |

If you are running an older version, upgrade to the latest release before reporting a security issue unless the issue prevents upgrading safely.

## Reporting a Vulnerability

Please do not report security vulnerabilities through public GitHub issues, pull requests, discussions, or any other public channel.

Report vulnerabilities privately by email to:

- `ahansardarvis@gmail.com`

When reporting, include as much of the following as possible:

- a clear description of the issue
- affected version and environment
- steps to reproduce
- proof of concept, screenshots, or logs if available
- impact assessment
- any suggested mitigation or fix

What to expect after reporting:

- Initial acknowledgement target: within 7 days
- Status updates: provided when the report is triaged and when a fix plan is available
- If the report is accepted: the issue will be validated, fixed, and disclosed after a patch or mitigation is available
- If the report is declined: you will be told why, for example if the behavior is not reproducible, is out of scope, or requires an unsafe local configuration

## Scope

Security reports are especially relevant for issues involving:

- unintended local command or action execution
- privilege escalation
- unsafe file access or deletion
- exposure of secrets, tokens, or private data
- insecure updater behavior
- dangerous browser or automation behavior triggered without clear user intent

General setup help, dependency installation problems, and ordinary functional bugs should be reported through the normal project channels instead of the security contact.
