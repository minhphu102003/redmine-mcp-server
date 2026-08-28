# Member Rules Catalog

Researched rule areas per role (ask the user which apply; do NOT assume any apply):

| Role | Typical rule areas |
|---|---|
| Backend | API-first contract (OpenAPI), schema/validation, authn/z + PII handling, error handling, database access rules, performance/scalability, test coverage |
| Frontend (web) | Design system + tokens, responsive + accessibility, performance (bundle/lazy), state management pattern, API contract alignment, e2e for critical flows |
| Mobile | Platform (native Swift/Kotlin vs Flutter/React Native), offline/caching + network retries, store policies + signing/release, crash monitoring, performance (cold start, memory, battery), secure storage |
| DevOps | CI/CD quality gates, IaC (Terraform/Ansible), Docker/K8s, observability/alerting, release management + rollback, security gates, secrets handling |
| AI (LLM) | RAG + evals (golden datasets), prompt management, guardrails, inference latency/cost, drift monitoring, model API rate limits/retries/fallbacks |
| Data analyst (DA) | SQL + BI dashboards, metric definitions, data quality/freshness, source of truth |
| Data engineer | dbt models, orchestration (Airflow), lineage, data quality tests, schema migrations |
| QA | Test pyramid, page objects/factories, e2e on critical paths only, adversarial/negative paths, contract testing |
| Full-stack | Both sides of the API contract, end-to-end feature ownership incl. tests |
| Lead (Tech/Team/Project) | Architecture decisions + review/approval gates (review rules, who must approve PRs/merge), task delegation (what they assign vs. keep), technical risk ownership, mentoring/onboarding, reporting to stakeholders, definition of done enforcement |
| Security | Threat modeling, SAST/DAST, auth, compliance |
| SRE | SLOs, error budgets, incidents, chaos testing |
| PM/PO | Intent + acceptance criteria + out-of-scope, definition of ready |

Cross-role dimensions to ask once per person: commit/branch conventions, code-review expectations, AI-assistant usage policy (allowed? verify output?), reporting cadence (standup/weekly), definition of done, preferred communication.
