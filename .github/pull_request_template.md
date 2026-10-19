## Summary
- Describe clearly what this PR changes.
- Link the main goal (feature, refactor, bugfix, cleanup).

## Release Scope
- Release: `v0.1.0`
- Type: `backend`
- Impacted areas:
  - [ ] API endpoints
  - [ ] Management commands
  - [ ] Export utilities
  - [ ] Data scripts
  - [ ] Infra/config

## Why
- Why is this change needed?
- What issue, risk, or improvement does it address?

## What Changed
- High-level list of implemented changes.
- Mention moved/removed files when relevant.

## Validation
- [ ] `python manage.py check`
- [ ] Local smoke test of impacted endpoints/commands
- [ ] No sensitive files included (`.env`, credentials)

### Commands executed
```bash
python manage.py check
# add any other command you ran
```

## Breaking Changes
- [ ] No breaking changes
- [ ] Yes (describe):

## Rollback Plan
- How to revert quickly if something fails in production.

## PR Hygiene Checklist
- [ ] Branch is up to date with `develop`
- [ ] Commits are atomic and descriptive
- [ ] Files unrelated to scope were not modified
- [ ] `.gitignore` rules respected
- [ ] Documentation/release notes updated

## Versioning
- Planned tag: `v0.1.0`
- Suggested merge strategy:
  - [ ] Squash and merge
  - [ ] Merge commit

## Notes for Reviewer
- Areas that need extra attention.
- Known limitations or pending follow-ups.
