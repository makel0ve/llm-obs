# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 1.x     | ✅        |

## Reporting a Vulnerability

Please **do not** open a public GitHub issue for security vulnerabilities.

Email us at **security@llm-obs.io** with:

- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

We will respond within **48 hours** and provide a fix timeline.

## Security Best Practices

When deploying LLM Obs:

- Use a strong random `SECRET_KEY` (minimum 32 characters)
- Never expose PostgreSQL, Redis, or MinIO ports publicly
- Rotate API keys regularly via the projects API
- Use HTTPS in production (put LLM Obs behind a reverse proxy like nginx or Caddy)
- Keep Docker images updated
