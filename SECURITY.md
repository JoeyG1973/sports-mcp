# Security policy

## Threat model

`sports-mcp` is designed to run on a trusted LAN as a back-end for Home
Assistant Voice. It exposes an unauthenticated SSE endpoint and
deliberately performs no authentication or rate-limiting of its own.

Do **not** expose the SSE port to the public internet. Anyone who can
reach the port can invoke the four read-only tools and indirectly trigger
outbound calls to ESPN's public API.

## Supported versions

Only the current `main` branch and the latest tagged release receive
security fixes. There are no LTS branches.

## Reporting a vulnerability

Please report security issues **privately** rather than opening a public
issue:

- Use GitHub's [private vulnerability reporting](https://github.com/JoeyG1973/sports-mcp/security/advisories/new)
  via the **Security** tab on this repository.

You should expect an acknowledgement within a few days. Once the issue
is confirmed, a fix and a coordinated disclosure timeline will follow.

## Scope

In scope:
- Server-side request forgery against arbitrary hosts via crafted inputs
- Crashes or denial of service from malformed responses
- Information leakage from cached responses across requests
- Dependency vulnerabilities in `httpx` or `mcp` that affect this project

Out of scope:
- Reachability of the SSE port from untrusted networks (this is the
  operator's responsibility — see threat model above)
- Issues that depend on a malicious local user with shell access
- Issues in ESPN's upstream API
