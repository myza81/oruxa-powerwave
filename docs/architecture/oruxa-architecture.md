# Oruxa VPS Application Architecture Design

## 1. Purpose

This document defines the architecture principles for hosting and developing multiple applications under `oruxa.uk`.

The main design goal is **maximum flexibility and portability**. Any major component should be movable to another VPS, server, cloud provider, managed service, or deployment platform with minimal application-code changes.

> **Preferred migration model: change configuration, endpoints, credentials, DNS, network, or deployment settings — not application logic.**

This architecture applies to Powerwave and future Oruxa-hosted applications.

---

## 2. Core Architecture Principles

Each application is a collection of loosely coupled components:

```text
Application
├── Frontend
├── Backend / API
├── Database
├── File / Object Storage
├── Authentication / Authorization
├── Background Services
└── Backups
```

Even when all components run on one VPS, they must be designed as if they could live on separate servers.

A second core principle applies to data:

> **Each application owns its own data domain. Other applications should normally consume that data through stable, versioned APIs rather than directly querying another application's database tables.**

Physical infrastructure may be shared. Application ownership must remain logically separated.

---

## 3. Deployment Model

### Initial deployment

```text
Internet
   ↓
Cloudflare DNS
   ↓
OVH VPS
   ↓
Caddy
   ↓
Docker
   ├── Powerwave frontend/backend
   ├── App2 frontend/backend
   ├── App3 frontend/backend
   └── Shared PostgreSQL infrastructure
          ├── powerwave_db
          ├── app2_db
          └── app3_db
```

### Future deployment

```text
powerwave.oruxa.uk      → Frontend server/CDN
api.powerwave.oruxa.uk  → Backend server
powerwave_db            → Dedicated/managed PostgreSQL
Powerwave files         → S3-compatible object storage
```

The application should continue working mainly through configuration changes.

---

## 4. VPS Directory Structure

```text
/srv/oruxa/
├── apps/
│   ├── powerwave/
│   ├── app2/
│   └── app3/
├── data/
│   ├── powerwave/
│   ├── app2/
│   └── app3/
├── infrastructure/
│   ├── postgres/
│   ├── backups/
│   └── shared-services/
└── backups/
    ├── postgres/
    ├── application-data/
    └── configuration/
```

Application source, persistent application files, shared infrastructure, and backups must remain separated.

---

## 5. Configuration-Driven Design

Infrastructure locations must never be hard-coded into application logic.

Prefer:

```env
DATABASE_URL=postgresql://powerwave_user:...@postgres:5432/powerwave_db
API_BASE_URL=https://api.powerwave.oruxa.uk
STORAGE_TYPE=local
STORAGE_PATH=/srv/oruxa/data/powerwave
APP2_API_BASE_URL=https://api.app2.oruxa.uk
```

Future migration may change these values without changing business logic.

Stable DNS names should be used as abstraction points where practical.

---

## 6. Frontend Design

The frontend must not assume the backend runs on the same machine.

```text
Frontend
   ↓ HTTPS API
Backend
```

The backend endpoint must be configurable.

---

## 7. Backend and API Design

Backends should remain as stateless as practical and expose stable, versioned APIs.

Examples:

```text
/api/v1/events
/api/v1/assets
/api/v1/measurements
/api/v1/analysis
```

APIs should expose meaningful domain resources, not generic database-table access.

Avoid:

```text
GET /database/table/assets
```

Prefer:

```text
GET /api/v1/assets/{id}
```

This allows internal database schemas to evolve without breaking API consumers.

---

## 8. Shared PostgreSQL Architecture

PostgreSQL is shared infrastructure, but each application should normally own a separate logical database.

```text
Shared PostgreSQL Server
│
├── powerwave_db
│     └── powerwave_user
├── app2_db
│     └── app2_user
└── app3_db
      └── app3_user
```

This is **shared physical infrastructure**, not one shared application database.

Each application should have its own:

- database
- database user
- credentials
- migration history
- backup scope
- data ownership boundary

Rules:

- PostgreSQL port `5432` must not be publicly exposed.
- Use private Docker networking while services share one VPS.
- Use secure private networking/TLS/VPN/firewall controls when databases move elsewhere.
- Use Alembic or equivalent schema migrations.
- One application's DB user should not normally have access to another application's DB.
- Application deployments should not restart the shared PostgreSQL service unnecessarily.

---

## 9. Independent Database Migration

Each application's database must be independently movable.

```text
Before:
Shared PostgreSQL
├── powerwave_db
└── app2_db

After:
PostgreSQL Server A
└── app2_db

PostgreSQL Server B
└── powerwave_db
```

Only the affected application's `DATABASE_URL` should normally need to change.

---

## 10. Application Data Ownership

Each application is the authoritative owner of its own domain data.

Example:

```text
App2
├── App2 API
└── app2_db
```

If App3 needs App2 data, the normal path should be:

```text
App3 backend
      ↓
App2 API
      ↓
app2_db
```

not:

```text
App3
      ↓
direct SQL
      ↓
app2_db tables
```

This avoids hidden coupling between applications.

---

## 11. Cross-Application Data Sharing

Cross-application sharing should normally use stable APIs.

Example:

```text
App3
  ↓
https://api.app2.oruxa.uk/api/v1/assets
  ↓
App2 API
  ↓
app2_db
```

Benefits:

- clear ownership
- independent schema evolution
- independent application migration
- independent database migration
- centralized validation and business rules
- better security and auditing
- stable contracts for consuming apps

If App2 later moves to another VPS or database server, App3 should normally continue using the same API endpoint.

### Versioning

Use versioned API contracts:

```text
/api/v1/...
```

Future incompatible changes may introduce:

```text
/api/v2/...
```

without immediately breaking existing consumers.

---

## 12. Direct Cross-Database Access

Direct access to another application's database should be an **exception**, not the normal design.

Possible justified cases:

- high-volume internal analytics
- specialized reporting
- controlled read-only extraction
- temporary migration work

If necessary, use a dedicated least-privilege read-only user or controlled database view.

Do not create undocumented permanent dependencies on another application's internal tables.

---

## 13. Future Shared Data Platform / Data Lake

The API-first application model is not itself a data lake.

A true shared data platform or data lake may be introduced later if several applications require:

- cross-application analytics
- large historical datasets
- AI/ML processing
- centralized reporting
- common reference datasets
- long-term analytical storage

Possible future model:

```text
Powerwave ─┐
App2      ─┼──→ Shared Data Platform / Data Lake
App3      ─┘
```

This should only be introduced when a genuine shared analytical requirement exists.

Until then:

> **Application databases remain application-owned; operational cross-app data sharing normally occurs through APIs.**

---

## 14. File and Object Storage

Application code must not depend on a permanent local filesystem path.

Current example:

```env
STORAGE_TYPE=local
STORAGE_PATH=/srv/oruxa/data/powerwave
```

Future example:

```env
STORAGE_TYPE=s3
STORAGE_ENDPOINT=https://...
STORAGE_BUCKET=powerwave
```

This allows migration to S3, R2, Backblaze B2, MinIO, NAS, or another storage server.

For Powerwave, original engineering files should remain immutable.

---

## 15. Reverse Proxy and DNS

Caddy is currently the public entry point.

Example:

```text
powerwave.oruxa.uk
api.powerwave.oruxa.uk
app2.oruxa.uk
api.app2.oruxa.uk
```

Today these may all point to one VPS.

Later they may point to separate servers.

Applications must not depend on Caddy specifically.

---

## 16. Network Security

Only services that must be public should be exposed.

```text
Public Internet
   ↓
80 / 443
   ↓
Caddy
```

Do not publicly expose PostgreSQL, Redis, or private administrative interfaces.

---

## 17. Authentication and Authorization

At the current MVP stage, each application may manage its own authentication and authorization.

```text
powerwave.oruxa.uk
   ↓
Powerwave login
```

```text
app2.oruxa.uk
   ↓
App2 login
```

A central Oruxa portal or single-sign-on layer is intentionally deferred until a real requirement justifies it.

Authentication should nevertheless remain replaceable so a future OIDC/SSO provider can be introduced without redesigning business logic.

---

## 18. Secrets Management

Never commit real credentials or tokens.

Use environment/configuration files locally and commit only `.env.example`.

Later, secrets can move to Docker secrets, GitHub Actions secrets, Vault, cloud secret managers, or managed deployment platforms.

---

## 19. Deployment and CI/CD

GitHub is the source of truth for application code.

Preferred deployment model:

```text
Developer
   ↓
git push
   ↓
GitHub
   ↓
CI/CD
   ↓
version-controlled deploy script
   ↓
immutable Git-SHA-tagged Docker image
   ↓
database migration
   ↓
container replacement
   ↓
health verification
```

Application deployments should not unnecessarily restart unrelated applications or shared infrastructure.

---

## 20. Monitoring and Logging

Backends should expose:

```text
/health
```

Logs should normally go to standard output.

Monitoring may later include database connectivity, storage availability, background workers, and important cross-application API dependencies.

---

## 21. Backup Architecture

Important data should have independent backups.

```text
Provider backup
+
PostgreSQL logical backup
+
Application file backup
+
Off-site backup
```

Each application database should remain independently restorable and migratable.

A backup is not considered reliable until restore has been tested.

---

## 22. Powerwave-Specific Direction

```text
Powerwave
├── Frontend
├── Backend / API
│   ├── file parsing
│   ├── COMTRADE processing
│   ├── signal calculations
│   ├── event synchronization
│   └── engineering analysis
├── Database
│   ├── users
│   ├── projects
│   ├── event metadata
│   └── analysis metadata
└── File Storage
    ├── original event files
    ├── processed datasets
    ├── exports
    └── reports
```

Original event records remain immutable.

If another Oruxa application needs Powerwave-owned information, it should normally call a Powerwave API rather than query Powerwave tables directly.

---

## 23. Migration Test

For every architectural decision ask:

> **If this component moves to another server tomorrow, what needs to change?**

Preferred answer:

```text
environment variables
DNS
credentials
network/firewall configuration
deployment configuration
```

Unacceptable answer:

```text
rewrite business logic
redesign database structures
change many source files
rewrite cross-application SQL
```

Also ask:

> **If App A changes its database schema tomorrow, will App B break?**

Preferred answer:

```text
No. App B depends on App A's versioned API contract, not App A's tables.
```

---

## 24. Architectural Rules

1. Frontend, backend, database, storage, and proxy remain logically separated.
2. Infrastructure details are externalized through configuration.
3. Avoid hard-coded IPs, ports, URLs, filesystem paths, and credentials.
4. Containers are disposable; persistent data is not.
5. Database schemas are managed through version-controlled migrations.
6. Components should be independently deployable and migratable.
7. Multiple apps may share one PostgreSQL server.
8. Each app should normally have its own logical database and database user.
9. Shared physical infrastructure must not create hidden application coupling.
10. An app should not normally depend directly on another app's database schema.
11. Cross-application data sharing should normally use stable, versioned APIs.
12. APIs should expose domain/business contracts, not generic table access.
13. Cross-application API endpoints must be configurable.
14. Direct cross-database access requires explicit justification and least privilege.
15. A true shared data platform/data lake should be introduced only when justified.
16. Individual app databases must remain independently migratable and restorable.
17. PostgreSQL must not be publicly exposed.
18. Secrets must not be stored in source control.
19. GitHub is the source of truth for code.
20. Backups and restore procedures must be maintained and tested.
21. Provider-specific coupling should be minimized.
22. Application deployment should not unnecessarily control unrelated apps or shared infrastructure.
23. Stable DNS/service endpoints should be preferred over server-specific addresses.
24. Migration should normally require configuration changes, not application redesign.

---

## 25. Current Oruxa Development Direction

```text
Cloudflare DNS
      ↓
OVH VPS
      ↓
Caddy
      ↓
Docker
      ├── independent application stacks
      └── shared infrastructure
              ↓
          PostgreSQL
```

Development is focused on independent application endpoints:

```text
powerwave.oruxa.uk
app2.oruxa.uk
app3.oruxa.uk
```

A central `oruxa.uk` landing portal and central SSO are deferred until a future requirement justifies them.

---

## 26. Final Design Goal

```text
Single VPS today
      ↓
Shared physical infrastructure where efficient
      ↓
Clear app and data ownership boundaries
      ↓
Stable APIs between applications
      ↓
Separate services tomorrow
      ↓
Different servers/providers later
      ↓
Minimal application-code changes
```

The architecture should always favour:

**portability, separation, clear data ownership, stable interfaces, configuration-driven deployment, security, recoverability, and maintainability.**
