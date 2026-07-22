# CI Security Controls

## Secret scanning

The `security` workflow job installs `detect-secrets==1.5.0` and runs:

```bash
git ls-files -z | xargs -0 detect-secrets-hook --baseline .secrets.baseline --no-verify
```

This scans tracked files only and compares findings against the committed
baseline. `detect-secrets` stores hashed findings in `.secrets.baseline`; do not
print candidate secret values in CI logs.

When the scan fails:

1. Remove and rotate real secrets before updating the baseline.
2. For false positives, regenerate and audit the baseline locally:

```bash
python -m pip install detect-secrets==1.5.0
detect-secrets scan > .secrets.baseline
detect-secrets audit .secrets.baseline
git ls-files -z | xargs -0 detect-secrets-hook --baseline .secrets.baseline --no-verify
```

Commit `.secrets.baseline` only after the findings have been reviewed.

## Pinned GitHub Actions

Workflow `uses:` references are pinned to commit SHA with the source major tag
kept in a trailing comment, for example:

```yaml
uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4
```

To update a pinned action:

1. Resolve the intended tag to a commit SHA:

```bash
git ls-remote https://github.com/actions/checkout refs/tags/v4
```

2. Replace only the SHA, keep the comment matching the reviewed tag.
3. Review the upstream release notes before merging the update.
4. Run `git diff --check` and let CI verify the workflow.
