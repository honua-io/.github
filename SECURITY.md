# Security Policy

Honua takes the security of our software and services seriously. This policy applies to
all repositories in the [honua-io](https://github.com/honua-io) organization.

## Reporting a vulnerability

**Please do not report security vulnerabilities through public GitHub issues.**

Report suspected vulnerabilities to **security@honua.io**. If you prefer, you may use
[GitHub private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability)
on the affected repository (Security → Report a vulnerability).

Please include, where possible:

- A description of the vulnerability and its impact
- Steps to reproduce (proof-of-concept, affected endpoint/component, version/commit)
- Any relevant logs, screenshots, or configuration

## Our commitment (response targets)

| Stage | Target |
|---|---|
| Acknowledge receipt | within 3 business days |
| Initial assessment & severity | within 10 business days |
| Status updates | at least every 10 business days until resolved |
| Resolution / mitigation | prioritized by severity |

We will keep you informed throughout, credit you (with your consent) once resolved, and
coordinate disclosure timing with you.

## Safe harbor

We will not pursue or support legal action against researchers who, in good faith:

- Make a reasonable effort to avoid privacy violations, data destruction, and service
  degradation
- Only interact with accounts they own or have explicit permission to access
- Do not exploit a finding beyond what is necessary to demonstrate it
- Report promptly and give us a reasonable opportunity to remediate before disclosure
- Do not access, modify, or exfiltrate customer data

Activities conducted consistent with this policy are considered authorized, and we will
not recommend or pursue legal action related to such research.

## Scope

In scope: the Honua platform and the source repositories under the honua-io organization.
Out of scope: third-party services and sub-processors (report those to the respective
vendor), volumetric denial-of-service testing, social engineering, and physical attacks.

## Supported versions

Security fixes are applied to the latest released version and the `trunk` development
branch. Older versions may not receive fixes.
