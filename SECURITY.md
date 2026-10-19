# Security Policy

## Supported versions

Security fixes go into the latest release of `testo-core` on PyPI and the `main` branch.
Older versions are not patched; upgrade to the latest release.

| Version | Supported |
|---------|-----------|
| latest `1.x` release | yes |
| older releases | no |

## Reporting a vulnerability

Please **do not open a public issue** for a security problem.

Report it privately through GitHub: open the repository's **Security** tab and choose
**Report a vulnerability** ([direct link](https://github.com/taltal-beep/testosterone/security/advisories/new)).
Include what you found, how to reproduce it, and the version (`testo --version`) or commit.

You can expect an acknowledgement within 7 days. Once the problem is confirmed, a fix is
released and the advisory is published with credit to you, unless you prefer to stay anonymous.

## Scope

In scope: the `testo` CLI, the `testo_core` engine, the FastAPI backend (`testo_api`), the
React frontend in `frontend/`, the GitHub Action and GitLab template, and the published
runner image.

Areas that deserve particular care:

- **Secrets in run artifacts.** Failure evidence (tracebacks, log tails) is redacted before it
  is stored or sent to an AI provider. A way to get an API key, token or password past that
  redaction is a vulnerability.
- **AI provider keys.** Keys pasted on the AI settings page are kept in memory only. Anything
  that writes them to disk, logs or API responses is a vulnerability.
- **API authentication.** Bypassing the API's token checks, or running commands through the
  API without the required permission.

Out of scope: problems in the test suites Testosterone runs for you (they run with your
permissions by design), and the deliberately broken demo app `fake-api`.
