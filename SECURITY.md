# Security Policy

## Supported Versions

Only the latest release (and the `main` branch) receives security updates.

## Reporting a Vulnerability

Please do **not** open a public issue for security vulnerabilities.

Instead, use one of these private channels:

- **GitHub private vulnerability reporting** (preferred):
  [Report a vulnerability](https://github.com/VibeVista/seojae/security/advisories/new)
- **Email**: laeyoung@comcom.ai

Include a description of the issue, steps to reproduce, and the potential impact.
You can expect an initial response within 7 days.

## Scope Notes

Seojae is a framework executed by LLM coding tools (Claude Code, Codex CLI,
Gemini CLI). Two areas deserve particular care:

- **Prompt injection via ingested sources** — content placed in `raw/` or fetched
  from connected wikis is processed by an LLM. Malicious instructions embedded in
  source documents are a known risk class for all LLM-driven tools; reports of
  injection paths that Seojae's schema or tools could mitigate are welcome.
- **Connected wikis** (`tools/connected_wikis.py`) — cloning external repositories
  executes no code by design, but reports of any path traversal, command
  injection, or consent-bypass issues in the connect/pull flow are high priority.
