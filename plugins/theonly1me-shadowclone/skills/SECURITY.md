# Security

Report failures in consent, redaction, repository scope, file ownership, or execution controls in private, with **Report a vulnerability** on the **Security** tab. Never put sensitive evidence in a public issue.

## What to report

- Source content that Shadowclone read without consent, or sent outside an authorized provider request.
- Secrets, excluded tool results, or private source that learning, logs, errors, or published files exposed.
- Guidance that applied outside its repository or organization scope, or actions without the required authorization.
- User configuration that overrode managed policy, or writes and deletions that bypassed ownership checks.

Include a synthetic reproduction and the affected version. There is no bounty and no guaranteed response time. Report a missing token pattern in public with a synthetic description, such as a token prefix and its length.

## Supported releases

Before version 1.0, security fixes target the newest release. Published npm packages include provenance. Check it against the [release workflow](.github/workflows/release.yml).
