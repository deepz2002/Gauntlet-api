# Development and submission notes

## Requirements, decisions and AI coding assistance

The security rules and fictional inventory come from the Developer Selection
Assignment. I supplied that assignment together with my development approach,
chosen technology stack, expected check behavior and frontend workflow. I used
OpenAI Codex as a coding tool to turn those specifications into working code and
to help with tests, debugging, Docker configuration and documentation.

My inputs included the modular scanner/registry approach, PostgreSQL persistence,
scan lifecycle and scoring requirements, and the interface behavior: a welcome
screen, scanning all clouds without an initial selection, skeleton loading,
collapsible scan history, and an API activity drawer. I refined the implementation
through follow-up requirements and corrections during development.

| Area | Specification and direction supplied | Coding assistance used |
| --- | --- | --- |
| Scanner | Ten assignment rules, statuses, permission-error handling, snapshot-based key age and worker limit | Implemented evaluators, shared validation, registry and concurrent execution |
| API | Six endpoints, background execution, account selection, scoring, filters and pagination | Implemented schemas, routes, services, repository queries and failure handling |
| Database | Persist scans/findings in local PostgreSQL with migrations | Implemented SQLAlchemy models, constraints, indexes and Alembic migration |
| Frontend | React/Tailwind layout and the scan, results, history and API-drawer interactions | Implemented components, real API requests, polling, filters and loading/error states |
| Verification | Check assignment edge cases and confirm the full flow | Wrote and executed unit/integration/component tests, lint/type checks and smoke scans |
| Packaging | Local Docker stack, non-root images, health checks and automatic migrations | Implemented Dockerfiles, Nginx proxy, Compose dependencies and CI workflow |
| Documentation | Explain setup, schema, security rules and deployment design | Assisted with README, Mermaid schema and DEPLOY.md wording |

AI assistance covered implementation across these modules. The requirements and
implementation direction above describe my inputs; the coding-assistance column
describes how the tool was used to realize them.

## Validation evidence

- 98 backend tests passed, including actual PostgreSQL integration tests.
- 15 frontend tests passed; Ruff, ESLint, TypeScript and the production build passed.
- Both application images built and ran as non-root users with health checks.
- Fresh-volume startup applied migrations automatically. A full snapshot scan
  produced 49 findings (27 PASS, 17 FAIL, 5 CANNOT_SCAN), with score 61.4.
- Scan results survived a PostgreSQL restart. Browser checks exercised the real API
  without embedded demo findings. No live cloud scanning or deployment was performed.
- [Verified GitHub Actions run for implementation commit 99cbdf5](https://github.com/deepz2002/Gauntlet-api/actions/runs/45463038051).
  The latest main-branch workflow is linked in README so subsequent commits can
  be checked separately; the fixed run link above is evidence for its named commit.

## Time spent by phase

Developer estimates have not yet been supplied. Enter the approximate active time
actually spent, rather than treating elapsed chat time as development time.

| Phase | Actual time / developer estimate |
| --- | --- |
| Requirements and planning | |
| Database and migrations | |
| Scanner and ten security checks | |
| REST APIs and persistence | |
| Frontend and integration | |
| Testing and verification | |
| Docker, CI and documentation | |

## Reviewer access and submission

- API: https://github.com/deepz2002/Gauntlet-api
- Frontend: https://github.com/deepz2002/Gauntlet-ui
- Both repositories were verified as public; reviewers can inspect them without
  invitations. The API pins the frontend as a submodule.
- Clone with `git clone --recurse-submodules https://github.com/deepz2002/Gauntlet-api.git`.
- Environment files, local dependencies, build output and browser artifacts are
  excluded from version control. A staged-file review found no common private-key,
  AWS access-key or GitHub-token patterns. The Compose password is fictional
  and for local development only.
- Repository submission by email has not been performed.
