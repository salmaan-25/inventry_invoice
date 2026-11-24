---
name: billing-inventory-backend-engineering
description: Strict, model-independent backend engineering rules for the Billing and Inventory Management System V1 using Django, Django REST Framework, PostgreSQL, Redis, and related backend technologies. Use for all backend planning, implementation, refactoring, debugging, testing, and code review.
---

# Backend Engineering Skill — Billing & Inventory Management System V1

## 1. Purpose and authority

This file defines mandatory engineering rules for every AI coding agent working on this backend. It is model-independent and intended for Gemini, Claude, OpenCode, DeepSeek, GLM, and other coding assistants.

Follow instructions in this order:
1. Explicit user instructions for the current task.
2. Approved V1 requirements and workflows.
3. This engineering skill.
4. Existing project conventions, provided they do not conflict with the above.

Do not interpret a technical suggestion as permission to expand product scope.

**Objective:** Build a correct, secure, maintainable, testable, and deployable backend. Keep V1 simple without sacrificing sound engineering. Optimize for correctness, clarity, and maintainability—not maximum abstraction or code volume.

## 2. Non-negotiable rules

1. **Understand before changing.** Inspect the repository, relevant files, dependencies, models, routes, tests, and conventions before implementing.
2. **Do not assume.** Ask when a business rule, requirement, or document format is unclear and the decision is consequential.
3. **Stay within scope.** Implement only the requested task and approved V1 requirements.
4. **Work incrementally.** Complete the current approved task or phase before moving on.
5. **Preserve working code.** Do not rewrite, rename, reorganize, or replace unrelated code.
6. **Keep changes focused.** Avoid unrelated formatting, dependency upgrades, and broad refactors.
7. **Use consistent patterns.** Do not introduce a second architecture for the same responsibility.
8. **No fake completion.** Never claim tests, migrations, integrations, or deployment succeeded unless actually run and verified.
9. **No silent shortcuts.** Never bypass validation, permissions, transactions, or tests to make a feature appear to work.
10. **Explain important decisions.** Report material assumptions, trade-offs, and unresolved issues.

## 3. Technology and architecture

### Expected stack
- Python
- Django
- Django REST Framework (DRF)
- PostgreSQL as the primary relational database and source of truth
- Redis only for justified caching, throttling, or coordination needs
- Django ORM for normal database operations
- A supported production application server and deployment configuration
- Automated tests using the project's selected test framework

Do not add Celery, message brokers, search engines, GraphQL, microservices, or other infrastructure unless an approved requirement needs them.

Before adding a dependency, explain what it solves, why the existing stack is insufficient, and its operational/maintenance cost. Prefer stable, maintained, compatible versions. Do not upgrade dependencies as part of an unrelated feature.

### Architecture principles
- Use a **modular monolith** for V1.
- Organize code by business domain and responsibility.
- Separate HTTP/API concerns from business rules and persistence concerns where this provides real value.
- Keep Django apps cohesive; do not create an app for every small model or utility.
- Avoid circular imports and hidden cross-app dependencies.
- Keep business rules out of views and avoid using signals as the default mechanism for core workflows.
- Do not create generic frameworks or abstractions for hypothetical future requirements.
- Do not split the system into services without explicit approval.

## 4. Project organization

Use a predictable structure. Adapt names to the approved domains, but preserve responsibility boundaries.

Recommended starting structure:

```text
backend/
├── manage.py
├── pyproject.toml                 # or the repository's chosen dependency file
├── .env.example
├── README.md
├── config/
│   ├── settings/
│   │   ├── base.py
│   │   ├── development.py
│   │   └── production.py
│   ├── urls.py
│   ├── asgi.py
│   └── wsgi.py
├── apps/
│   ├── common/
│   ├── accounts/
│   ├── company/
│   ├── customers/
│   ├── products/
│   ├── inventory/
│   ├── invoices/
│   ├── payments/
│   ├── delivery/
│   ├── expenses/
│   ├── other_income/
│   └── dashboard/
├── tests/
└── scripts/
```

Do not create every app on day one. Create an app when its phase begins and its responsibility is understood.

For a domain app that needs separation, use a structure such as:

```text
apps/invoices/
├── admin.py
├── apps.py
├── models/
│   ├── __init__.py
│   └── invoice.py
├── api/
│   ├── serializers.py
│   ├── views.py
│   ├── urls.py
│   └── permissions.py
├── services/
│   └── invoice_service.py
├── selectors/
│   └── invoice_selectors.py
├── migrations/
└── tests/
    ├── test_models.py
    ├── test_services.py
    └── test_api.py
```

Structure rules:
- Do not create empty directories or placeholder modules without a current need.
- Small apps may use single files initially. Split them when size or responsibility justifies it.
- Keep shared utilities in `common` only when genuinely shared and domain-neutral.
- Do not put invoice-specific or inventory-specific logic in `common`.
- Avoid dumping unrelated functions into `utils.py`, `helpers.py`, or `misc.py`.
- Keep settings, environment configuration, routing, and deployment concerns outside business-domain apps.
- Keep test organization consistent across the repository.

## 5. Responsibility boundaries

### Models
Models define persisted data, relationships, constraints, and small domain-level behavior.
- Use explicit field types, lengths, nullability, defaults, and related names.
- Add database constraints and indexes when justified by invariants or query patterns.
- Keep model methods small and deterministic.
- Do not put large multi-step workflows in model methods.
- Do not rely only on frontend validation for data integrity.

### Serializers
Serializers handle API input validation and output representation.
- Validate user input at the API boundary.
- Use separate create/update/read serializers when responsibilities differ.
- Keep serializers focused; do not put large business workflows in them.
- Never trust client-supplied calculated totals, stock values, balances, ownership identifiers, or protected status transitions.
- Ensure write serializers cannot modify server-controlled fields.

### Views / ViewSets
Views handle HTTP concerns and coordinate requests.
- Keep views thin: authentication, permissions, validation, service invocation, and response handling.
- Do not put complex calculations or multi-model workflows directly in views.
- Avoid repeating orchestration logic across endpoints.

### Services
Services contain explicit business operations and workflows.
- Use them for multi-step actions, state transitions, calculations, and operations involving multiple models.
- Give functions clear names and narrow responsibilities.
- Pass required data explicitly; avoid hidden request or global state.
- Use database transactions for operations that must succeed or fail as a unit.
- Make important operations safe against accidental duplicate execution where appropriate.

### Selectors / query functions
- Use selectors for reusable or substantial read/query logic.
- Use `select_related` and `prefetch_related` where appropriate.
- Avoid loading entire tables when only a subset is needed.
- Do not create a selector layer for trivial one-line queries unless it improves consistency.

### Permissions
- Enforce access on the backend, not only in the frontend.
- Apply authentication and object-level access checks wherever relevant.
- Scope querysets to the authenticated user's permitted business/account.
- Never trust a client-provided business, owner, or staff ID to establish access.
- Deny access by default when authorization cannot be established.

### Utilities
Utilities must be small, reusable, and independent of a specific request. Do not use them to hide business logic or create circular imports.

## 6. Naming, readability, and code quality

- Use `snake_case` for Python modules, functions, variables, and fields.
- Use `PascalCase` for classes.
- Use clear, domain-specific names; avoid unexplained abbreviations.
- Keep functions focused on one responsibility.
- Keep nesting and branching manageable.
- Avoid giant functions, serializers, views, models, and files.
- Avoid clever one-liners when ordinary code is clearer.
- Do not duplicate business rules. Extract shared logic only when it is genuinely shared.
- Keep reusable code independent of HTTP request objects wherever practical.
- Avoid hidden side effects in properties, serializers, signals, and utility functions.
- Do not create generic base classes or abstractions solely to avoid a few repeated lines.
- Do not add comments that merely restate code. Explain non-obvious business rules and trade-offs.
- Add docstrings to public or complex functions when they clarify purpose, inputs, outputs, or side effects.
- Use consistent formatting and linting conventions selected by the repository.
- Use type hints for service functions and complex reusable logic when they improve clarity.
- Remove dead code, unused imports, debug prints, commented-out implementations, and unexplained TODOs.

## 7. Database and data integrity

PostgreSQL is the source of truth.

- Use Django ORM for normal application access.
- Use migrations for every schema change. Review generated migrations before applying them.
- Never modify an already-applied migration to change production history; create a new migration.
- Use appropriate foreign keys, deletion behavior, unique constraints, check constraints, and indexes.
- Choose `on_delete` behavior deliberately; do not use `CASCADE` automatically.
- Use pagination for potentially large lists.
- Avoid N+1 queries.
- Use bulk operations only when their behavior and side effects are understood.
- Use raw SQL only when the ORM is unsuitable or a measured performance need justifies it. Always parameterize raw SQL.

### Money and quantities
- Use `DecimalField` for currency and precise decimal quantities.
- Never use Python `float` for money calculations.
- Define precision and rounding deliberately.
- Do not invent tax, discount, or rounding rules. Follow the client's supplied invoice format and confirmed rules.
- V1 uses INR unless approved requirements change.
- Validate quantity and monetary inputs on the server.
- Calculate authoritative totals on the backend.

### Historical records
- Preserve the historical information needed to reproduce issued invoices and finalized business documents.
- Editing a customer or product must not silently alter historical documents.
- Store snapshots of descriptions, prices, tax details, and other document values when required by the approved workflow.
- Do not routinely hard-delete finalized financial or inventory records.
- Do not invent cancellation, reversal, refund, or credit-note workflows.

### Transactions and concurrency
Use `transaction.atomic()` for all-or-nothing operations, including:
- Issuing an invoice and deducting stock.
- Recording a payment and allocating it to an invoice.
- Creating/updating related records that form one business operation.

For stock and payment operations:
- Consider concurrent requests and race conditions.
- Use appropriate row locking, conditional updates, constraints, or idempotency controls where required.
- Prevent duplicate stock deductions and duplicate payment processing.
- A disabled frontend button is not duplicate-request protection.
- Keep transaction boundaries explicit and as small as practical.
- Do not perform slow external network calls while holding database locks.

### Approved V1 inventory rules
- Goods and Goods (Hardware) are stock-tracked.
- Service items are not stock-tracked.
- Draft invoices do not deduct stock.
- Issuing an invoice deducts stock exactly once for applicable items.
- A delivery challan must not deduct stock a second time.
- Partial delivery must not exceed the remaining undelivered quantity.
- Do not permit negative stock by default.
- Validate stock availability during the authoritative transaction, not only when a draft is created.
- Record stock movements in a traceable manner consistent with the approved design.

Do not change these rules without explicit user approval.

## 8. API design

Use DRF consistently and design APIs around clear resources and actions.

- Use predictable URL naming and HTTP methods.
- Use plural resource names for collections.
- Use `GET` for reads, `POST` for creation/actions, and `PUT`/`PATCH` for updates according to the repository convention.
- Use `DELETE` only where deletion is allowed.
- Use appropriate HTTP status codes and consistent validation errors.
- Paginate list endpoints that can grow.
- Add filtering, searching, and ordering deliberately; do not add arbitrary query parameters.
- Do not expose internal model fields or database implementation details.
- Do not expose stack traces or raw exception details to clients.
- Validate state transitions on the server.
- Use explicit action endpoints for operations such as issuing a document or recording a payment. Do not let clients update protected status fields directly.
- Keep list and detail endpoints under the same access boundaries.
- Document endpoint behavior.
- Add API versioning only when the project requires it.

Follow the response convention already established. If none exists, define one before implementing multiple endpoints and use it consistently. Do not add a custom response envelope merely for appearance; standard DRF responses are acceptable.

### Errors
- Return field-level validation errors where possible.
- Use clear, actionable messages without leaking sensitive information.
- Handle expected business-rule failures explicitly.
- Do not use broad `except Exception` blocks to hide defects.
- Log unexpected exceptions through configured logging and return a safe response.
- Never return HTTP 200 for a failed operation.

## 9. Authentication, authorization, and security

- Use Django-supported authentication and a deliberate DRF authentication configuration.
- Use a custom user model from the beginning if the approved design requires it; do not casually switch after migrations or production data exist.
- Hash passwords using Django's password-hashing facilities. Never store plaintext passwords.
- Never hardcode secrets, API keys, database passwords, or tokens.
- Store secrets in environment variables or the deployment platform's secret manager.
- Keep `.env.example` limited to variable names and safe placeholders.
- Exclude `.env`, private keys, local databases, and secrets from version control.
- Configure `DEBUG=False`, allowed hosts, secure cookies, HTTPS behavior, and production security settings appropriately.
- Validate and normalize user input.
- Use ORM parameterization; never build SQL from user input through string concatenation.
- Apply least privilege to database and application credentials.
- Protect sensitive endpoints with authentication and permissions.
- Set CORS and CSRF policies for the actual frontend/authentication approach; never use wildcard origins as a production shortcut.
- Validate upload size, file type, and content if uploads are introduced.
- Never log passwords, tokens, session identifiers, or unnecessary sensitive customer data.
- Do not disable security checks without clearly limiting the change to development.

V1 staff access is basic. Do not invent a complex permission matrix. Confirm actual roles and access rules before implementing them.

## 10. Redis and caching

Redis is not the primary database.

- PostgreSQL remains the source of truth.
- Use Redis only for a clear requirement such as caching, throttling, or coordination.
- Never store the only copy of business-critical information in Redis.
- Define cache keys consistently and include relevant identifiers/versioning.
- Set appropriate TTLs; avoid indefinite caching unless justified.
- Invalidate or update cache entries when underlying data changes.
- Do not cache sensitive data without a clear security and isolation design.
- Scope cache entries by business/user where cross-account leakage is possible.
- Do not cache every endpoint by default.
- Do not add Redis code to a task that does not need it.
- Define safe behavior when Redis is unavailable: fail safely or use an approved fallback.
- Never use Redis as a replacement for database transactions or constraints.

## 11. Background jobs and external integrations

- Keep short, reliable request-response workflows synchronous.
- Introduce a background task system only for work that is slow, retryable, scheduled, or unsuitable for a request.
- Do not add Celery or another worker system without approval.
- Make retryable tasks idempotent; define retry limits and failure handling.
- Do not report success before the actual outcome is known.
- Keep external credentials in environment configuration.
- Set connection and request timeouts.
- Handle external service failures explicitly.
- Avoid holding database transactions open while waiting for external services.
- Do not create mock integrations that appear production-ready.

## 12. Dates, timezone, and exports

- Use timezone-aware datetimes.
- Use Asia/Kolkata as the current V1 business timezone.
- Store and compare timestamps consistently; do not mix naive and aware datetimes.
- Use DD/MM/YYYY at the presentation boundary.
- Expenses and Other Income exports must include both From Date and To Date.
- Reject a range where From Date is later than To Date.
- Generate genuine `.xlsx` files for approved Excel exports; do not silently substitute CSV.
- Do not include records outside the requested date range.
- Avoid loading unbounded records into memory for large exports; use an appropriate iteration/streaming strategy when needed.

## 13. Logging and operations

- Use Python's `logging` module and Django logging configuration.
- Choose appropriate log levels.
- Include useful operational context without exposing secrets or unnecessary personal data.
- Do not use `print()` for production logging.
- Do not swallow exceptions silently.
- Keep development and production settings separate.
- Add health/readiness behavior only as required by deployment.
- Configure database connections and static/media handling for the actual deployment platform.
- Keep deployment instructions in the README.
- Do not add a complex monitoring stack without an approved operational need.

## 14. Testing

Tests are part of implementation, not optional cleanup.

Test relevant layers:
- Model constraints and behavior.
- Serializer validation.
- Service/business logic.
- API authentication and permissions.
- API success and failure responses.
- Transaction behavior for critical workflows.
- Boundary cases and duplicate requests.
- Filtering, pagination, and exports where applicable.

Cover relevant business-critical scenarios:
- Service items do not affect stock.
- Goods and Goods (Hardware) use stock tracking.
- Draft invoice creation does not deduct stock.
- Invoice issue deducts stock exactly once.
- Repeated issue requests cannot deduct stock twice.
- Delivery challan does not deduct stock a second time.
- Partial delivery cannot exceed remaining quantity.
- Payment allocation follows approved outstanding-balance rules.
- Client-submitted totals cannot override backend calculations.
- Users cannot access records outside their permitted business/account.
- Export date boundaries include both requested dates.

Test rules:
- Use isolated test data and a test database.
- Do not rely on test execution order.
- Do not call real external services in ordinary automated tests.
- Mock external boundaries, not the business logic under test.
- Use factories or fixtures consistently if adopted.
- Make meaningful assertions; do not merely assert that a response exists.
- Run relevant tests after changes and report exactly what ran and what did not.

## 15. Performance and maintainability

- Identify a credible bottleneck before adding optimization complexity.
- Avoid N+1 queries and unbounded querysets.
- Add indexes based on actual filtering, sorting, joining, or uniqueness needs.
- Paginate growing collections.
- Avoid repeated database queries inside loops.
- Avoid premature caching, raw SQL, and denormalization.
- Keep response payloads appropriate to each endpoint.
- Prefer simple, readable solutions over speculative optimization.

## 16. Documentation and repository hygiene

The README should cover, as applicable:
- Project purpose and backend stack.
- Prerequisites and environment setup.
- Dependency installation.
- PostgreSQL and Redis setup, if required.
- Migrations and development-user creation.
- Running the development server and tests.
- Important environment variables.
- Deployment notes.

Also:
- Keep `.env.example` updated.
- Document important API behavior and non-obvious business rules.
- Never document unimplemented features as if they exist.
- Keep dependency files accurate.
- Do not commit secrets, local databases, dumps, generated files, or unrelated artifacts.

## 17. Strict V1 scope protection

Implement only approved workflows, including:
- Basic authentication and staff access.
- Business settings.
- Customers.
- Products and item types: Goods, Goods (Hardware), Service.
- Stock tracking for Goods and Goods (Hardware), not Service.
- Invoice workflow using the client's supplied invoice format and confirmed rules.
- Payments and outstanding balances.
- Dedicated Delivery Challan workflow.
- Expenses and Other Income.
- Inclusive date-range Excel exports for Expenses and Other Income.
- Approved dashboard behavior.

Do not add the following without explicit approval:
- Quotations.
- Purchase and supplier management.
- Sales/purchase returns, credit notes, or debit notes.
- Invoice cancellation or reversal workflows.
- Payment refunds or void workflows.
- Advanced accounting or bank reconciliation.
- Multiple warehouses or barcode scanning.
- Complex staff roles and permission matrices.
- Payroll/HR, CRM, or messaging automation.
- Advanced analytics or multi-company support.
- E-invoicing or e-way bill integrations.
- Microservices, Kubernetes, or elaborate infrastructure.

Do not invent GST/tax calculations, invoice numbering/financial-year rules, discount/rounding behavior, payment allocation priorities, stock adjustment workflows, cancellation rules, or invoice layout details. Use the client's supplied sample and explicit decisions. If information is unavailable, stop at that decision point and ask.

## 18. Mandatory implementation workflow

### Step 1 — Inspect
- Inspect relevant repository structure and implementation.
- Read related models, serializers, views, services, URLs, settings, migrations, and tests.
- Identify conventions and dependencies.
- Check current Git changes when possible.
- Never overwrite uncommitted user work.

### Step 2 — Define
Briefly state:
- Requirement being implemented.
- Expected apps/files to change.
- Whether models or migrations are affected.
- API endpoints or service operations involved.
- Tests that will prove correctness.
- Any ambiguity or dependency requiring confirmation.

Keep the plan concise for small, unambiguous tasks.

### Step 3 — Implement
- Make the smallest complete change.
- Follow the existing architecture and naming conventions.
- Keep responsibilities separated.
- Add validation, permissions, and transactions where required.
- Add/update tests with the implementation.
- Update documentation when behavior or setup changes.
- Make no unrelated improvements.

### Step 4 — Verify
Run applicable checks available in the repository:
- Formatting/linting if configured.
- Django system checks.
- Migration checks.
- Relevant automated tests.
- Additional checks directly related to the change.

Inspect the final diff for accidental changes, unused code, missing migrations, security issues, and untested branches.

### Step 5 — Report
Report:
1. What was implemented.
2. Important files created or changed.
3. API endpoints or behavior added/modified.
4. Migrations created, if any.
5. Tests/checks actually run and their results.
6. Assumptions or unresolved decisions.
7. Required next action.

Never claim a command passed if it was not executed.

## 19. Phase discipline

Development is backend-first.
- Follow the agreed backend execution plan in order.
- Work only on the currently selected phase unless the user changes direction.
- Do not start frontend implementation during backend phases.
- Do not implement future modules early merely because they appear in the roadmap.
- Finish and verify the current phase before moving on.
- Keep the API contract clear for later frontend integration.
- At each phase boundary, summarize completed functionality, tests, migrations, API routes, and dependencies.

If a task crosses phase boundaries, explain why and ask before expanding the work.

## 20. Git and change management

- Do not run destructive Git commands.
- Do not reset, clean, force-push, or discard user changes without explicit permission.
- Do not commit unless asked or explicitly authorized by the established workflow.
- Keep changes focused and reviewable.
- Use clear commit messages when asked to commit.
- Never include secrets or local environment files in commits.
- Before recommending migrations or deployment, explain impact and data-safety considerations.

## 21. Prohibited coding-agent behavior

Never:
- Invent requirements or client decisions.
- Expand V1 scope without permission.
- Replace the approved stack without permission.
- Rewrite the entire project for a small feature.
- Put all logic in views, serializers, or one giant file.
- Create unnecessary layers, base classes, managers, mixins, factories, or generic frameworks.
- Duplicate business rules across endpoints.
- Trust frontend-calculated financial or inventory values.
- Bypass authorization or validation.
- Use floats for money.
- Perform critical multi-model workflows without appropriate transaction handling.
- Use Redis as the source of truth.
- Add dependencies or infrastructure without justification.
- Ignore failing tests or migrations.
- Hide errors with broad exception handling.
- Claim tests or deployment succeeded without running them.
- Modify unrelated files or user changes.
- Guess when a business-rule decision is unresolved.

## 22. Definition of done

A backend task is complete only when all applicable items are satisfied:

- [ ] The change matches the requested and approved requirement.
- [ ] Existing architecture and folder conventions are respected.
- [ ] Responsibilities are separated cleanly.
- [ ] Server-side validation is implemented.
- [ ] Authentication and authorization are enforced where applicable.
- [ ] Database integrity and transaction requirements are addressed.
- [ ] Migrations are created and reviewed when schema changes occur.
- [ ] Relevant tests are added or updated.
- [ ] Relevant checks have been run and results reported.
- [ ] API behavior and errors are consistent.
- [ ] No unrelated changes or unrequested features were introduced.
- [ ] Documentation and environment examples are updated when necessary.
- [ ] Remaining assumptions and limitations are clearly stated.

Code being written does not, by itself, mean the task is complete.

## 23. Default instruction to the coding agent

Apply this skill before every implementation task.

Work as a careful senior backend engineer: inspect first, understand the approved requirement, plan a focused change, implement cleanly, test it, and report verified results.

Prefer simple, explicit, maintainable Django and DRF code. Keep PostgreSQL authoritative. Use Redis only where justified. Protect business data with validation, permissions, constraints, and transactions. Follow approved V1 workflows exactly.

If a requirement is unclear, ask rather than inventing it. If an improvement is outside scope, explain it separately and wait for approval. Do not move to another phase until the current task is complete and verified.
