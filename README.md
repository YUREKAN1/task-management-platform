# Task Management & Team Collaboration Platform

A clean, modular REST API backend for task management, team collaboration, and transactional audit logging. Designed as an engineering-focused project demonstrating clean architecture, database modeling, role-based access control (RBAC), multi-criteria search/filtering/sorting, and automated testing.

Built with **FastAPI**, **SQLAlchemy**, **Pydantic v2**, and **PostgreSQL**.

---

## Table of Contents
1. [Project Overview](#project-overview)
2. [Key Features](#key-features)
3. [Technology Stack](#technology-stack)
4. [Architecture & Design](#architecture--design)
5. [Project Structure](#project-structure)
6. [Data Models & Schema](#data-models--schema)
7. [Authentication & Authorization (RBAC)](#authentication--authorization-rbac)
8. [Task Lifecycle & Business Rules](#task-lifecycle--business-rules)
9. [Audit Logging System](#audit-logging-system)
10. [API Endpoint Directory](#api-endpoint-directory)
11. [Local Setup & Getting Started](#local-setup--getting-started)
12. [Database Migrations](#database-migrations)
13. [Interactive API Docs & Swagger Workflow](#interactive-api-docs--swagger-workflow)
14. [Testing & Quality Assurance](#testing--quality-assurance)
15. [Key Engineering Decisions](#key-engineering-decisions)

---

## Project Overview

This platform provides a collaborative workspace where users can organize into teams, manage scoped projects, assign and track tasks with full state transitions, and monitor platform activity through an audit trail.

All mutations are transaction-consistent, protected by fine-grained permissions, and tested against a regression suite of **314 automated tests**.

---

## Key Features

- **Stateless Authentication**: JWT tokens with bcrypt password hashing, case-insensitive email normalization, and account deactivation.
- **Dual-Tier RBAC**:
  - **Global Roles**: `USER`, `ADMIN` (admin bypass for cross-team project/task oversight).
  - **Team Roles**: `MEMBER`, `MANAGER` (team managers control membership, projects, and task delegation).
- **Team Governance**: Self-service team creation, member onboarding, role promotion/demotion, and last-manager demotion/removal protection.
- **Project Organization**: Multi-tenant team projects with soft-deletion confirmation guards (`?confirm=true`).
- **Comprehensive Task Management**:
  - **Personal Tasks**: Private to individual users (`project_id = null`).
  - **Project Tasks**: Team-scoped tasks with delegation, status workflows, and priority levels.
  - **Status Invariant**: Automatic recording and resetting of `completed_at` timestamps.
- **Search, Filtering, Pagination & Sorting**:
  - Full-text search across titles and descriptions.
  - Multi-field filtering (status, priority, assignee, due date ranges).
  - Multi-column sorting (`created_at`, `updated_at`, `due_date`, `priority`, `status`, `title`) with deterministic secondary tie-breaking on `id`.
  - Zero-indexed, bounded pagination with total counts and page counts.
- **Transactional Audit Logging**: 17 platform mutation events captured atomically in the same database transaction with team-scoped access control.

---

## Technology Stack

- **Framework**: [FastAPI](https://fastapi.tiangolo.com/) (Python 3.11+)
- **Data Validation & Settings**: [Pydantic v2](https://docs.pydantic.dev/) & `pydantic-settings`
- **ORM**: [SQLAlchemy 2.0](https://www.sqlalchemy.org/)
- **Database Migrations**: [Alembic](https://alembic.sqlalchemy.org/)
- **Primary Database**: [PostgreSQL 17](https://www.postgresql.org/) (via Docker)
- **Security & Tokens**: [PyJWT](https://pyjwt.readthedocs.io/) & [Passlib](https://passlib.readthedocs.io/) (bcrypt)
- **Testing**: [Pytest](https://docs.pytest.org/) & HTTPX `TestClient` (isolated in-memory SQLite transactions)
- **Containerization**: Docker & Docker Compose

---

## Architecture & Design

The platform strictly adheres to a **layered service architecture**, decoupling transport protocols from business rules and persistence:

```
FastAPI Routers (app/api/endpoints/)
       │
       ▼
Pydantic Schemas (app/schemas/) [Input Validation & Response Serialization]
       │
       ▼
Service Layer (app/services/) [Business Logic, Authorization & Audit Events]
       │
       ▼
SQLAlchemy ORM Models (app/models/)
       │
       ▼
PostgreSQL Database (production/dev) / SQLite (tests)
```

1. **Routers (`app/api/endpoints/`)**: Handle HTTP serialization, status codes, query/path parameter extraction, and dependency injection (`get_current_user`, `get_db`).
2. **Services (`app/services/`)**: Contain core domain logic, authorization checks, state machine transitions, and database queries.
3. **Audit Logging**: Emitted from within services before `db.commit()` so audit records share the caller's transaction.
4. **Schemas (`app/schemas/`)**: Pydantic models with `model_config = ConfigDict(from_attributes=True)` ensuring clean request validation and response filtering (e.g. `password_hash` is never exposed).

---

## Project Structure

```
Task-Management/
├── alembic/                # Database migration scripts and versions
│   ├── versions/           # Alembic revision files
│   └── env.py              # Migration environment configuration
├── app/
│   ├── api/
│   │   ├── deps.py         # Dependencies: get_db, get_current_user, oauth2_scheme
│   │   └── endpoints/      # REST API route handlers
│   │       ├── auth.py     # Authentication & registration
│   │       ├── users.py    # User profile & account deactivation
│   │       ├── teams.py    # Team management & membership
│   │       ├── projects.py # Team projects & soft deletion
│   │       ├── tasks.py    # Personal/project tasks, search, filter, sort
│   │       ├── audit_logs.py # Audit log querying & filtering
│   │       └── health.py   # Liveness & database connectivity probes
│   ├── core/
│   │   ├── config.py       # Pydantic BaseSettings environment loader
│   │   ├── logger.py       # Centralized logging configuration
│   │   └── security.py     # Password hashing & JWT token issuance/decoding
│   ├── database/
│   │   └── session.py      # SQLAlchemy engine, session maker, Base declarative
│   ├── models/             # SQLAlchemy ORM entity models
│   │   ├── enums.py        # Domain Enums (Roles, Status, Priority, Actions)
│   │   ├── user.py         # User entity model
│   │   ├── team.py         # Team & TeamMember entity models
│   │   ├── project.py      # Project entity model
│   │   ├── task.py         # Task entity model
│   │   └── audit_log.py    # AuditLog entity model
│   ├── schemas/            # Pydantic request & response schemas
│   │   ├── token.py        # Token response
│   │   ├── user.py         # User schemas & validation
│   │   ├── team.py         # Team & membership schemas
│   │   ├── project.py      # Project schemas
│   │   ├── task.py         # Task schemas, filters, pagination
│   │   └── audit.py        # Audit log schemas & pagination
│   ├── services/           # Service-layer business logic
│   │   ├── auth.py         # Authentication service
│   │   ├── user.py         # User management service
│   │   ├── team.py         # Team governance & membership service
│   │   ├── project.py      # Project operations service
│   │   ├── task.py         # Task lifecycle, querying & assignment
│   │   └── audit.py        # Transactional audit logging service
│   └── main.py             # FastAPI app initialization & OpenAPI metadata
├── tests/                  # Pytest test suite (314 tests)
│   ├── conftest.py         # Fixtures: in-memory DB, rollback session, TestClient
│   ├── test_auth.py        # Authentication & JWT tests
│   ├── test_users.py       # Profile & deactivation tests
│   ├── test_teams.py       # Team & membership tests
│   ├── test_projects.py    # Project tests & admin bypass
│   ├── test_tasks.py       # Task lifecycle & assignment tests
│   ├── test_task_queries.py # Search, filtering & pagination tests
│   ├── test_task_sorting.py # Multi-column sorting & tie-breaking tests
│   ├── test_audit_logs.py  # Audit logging & RBAC scoping tests
│   ├── test_phase9.py      # Hardening, error codes & input validation tests
│   ├── test_phase10.py     # Cross-cutting quality & transaction integrity tests
│   ├── test_models.py      # ORM model integrity tests
│   └── test_health.py      # Health check tests
├── .env.example            # Sample environment variables
├── alembic.ini             # Alembic CLI configuration
├── docker-compose.yml      # PostgreSQL 17 container definition
├── requirements.txt        # Python dependency manifest
└── README.md
```

---

## Data Models & Schema

### Entity Relationship Summary

- **User**: Identified by UUID. Has `name`, `email` (unique, lowercase), `password_hash`, `global_role` (`USER` or `ADMIN`), `is_active`.
- **Team**: Has `name`, `description`, `created_by` (FK -> User).
- **TeamMember**: Join table connecting `team_id` (FK -> Team) and `user_id` (FK -> User) with `role` (`MEMBER` or `MANAGER`). Unique on `(team_id, user_id)`.
- **Project**: Has `name`, `description`, `team_id` (FK -> Team), `created_by` (FK -> User), `deleted_at` (soft deletion timestamp).
- **Task**: Has `title`, `description`, `status` (`TODO`, `IN_PROGRESS`, `COMPLETED`), `priority` (`LOW`, `MEDIUM`, `HIGH`), `due_date`, `completed_at`, `created_by` (FK -> User), `project_id` (FK -> Project, nullable for personal tasks), `assigned_to` (FK -> User, nullable).
- **AuditLog**: Has `actor_id` (FK -> User), `action` (Enum), `entity_type` (`user`, `team`, `project`, `task`), `entity_id` (UUID), `team_id` (FK -> Team, nullable), `description`, `metadata` (JSON), `created_at`.

---

## Authentication & Authorization (RBAC)

The application enforces a dual-tier authorization model:

### 1. Global Roles
- **`USER`**: Default role for all newly registered users. Can manage own profile, create personal tasks, and join/create teams.
- **`ADMIN`**: Platform administrators. Can view all audit logs, access any team project, and manage any project task regardless of team membership.

### 2. Team Roles
- **`MANAGER`**: Granted to team creators or promoted members. Can:
  - Add or remove team members.
  - Promote members to Manager or demote Managers to Member.
  - Create, update, and soft-delete team projects.
  - Create project tasks and assign them to team members.
- **`MEMBER`**: Can view team details, list team members, list team projects, view project tasks, and update status of tasks assigned to them. Cannot modify team rosters or projects.

### Authorization Matrix

| Action | Standard User | Team Member | Team Manager | Global Admin |
|---|:---:|:---:|:---:|:---:|
| Register / Login / View Self | Yes | Yes | Yes | Yes |
| Manage Personal Tasks | Yes (own only) | Yes (own only) | Yes (own only) | Yes (own only) |
| Create Team | Yes | Yes | Yes | Yes |
| View Team Roster | No | Yes | Yes | Yes |
| Add / Remove Team Member | No | No | Yes | Yes |
| Create / Delete Projects | No | No | Yes | Yes |
| Create / Delete Project Tasks | No | No | Yes | Yes |
| Assign Project Tasks | No | No | Yes | Yes |
| Update Status of Assigned Task | No | Yes (assignee) | Yes | Yes |
| Query Team Audit Logs | No | No | Yes (own team) | Yes (all teams) |

---

## Task Lifecycle & Business Rules

### Personal Tasks vs. Project Tasks
- **Personal Tasks**: Created via `POST /tasks`. Private to the owner (`project_id = null`). Cannot be assigned to other users (`PATCH /tasks/{id}/assignment` returns 400).
- **Project Tasks**: Created via `POST /projects/{project_id}/tasks`. Scoped to a project. Can be assigned only to active members of the project's parent team.

### State Transitions & `completed_at`
- **`TODO` -> `IN_PROGRESS`**: `completed_at` remains `null`.
- **`IN_PROGRESS` -> `COMPLETED`**: `completed_at` is automatically stamped with the current UTC datetime.
- **`COMPLETED` -> `TODO` or `IN_PROGRESS`**: `completed_at` is automatically cleared back to `null`.
- The `completed_at` field is strictly managed by the backend; client attempts to spoof completion timestamps in request bodies are ignored.

### Assignment Rules
- Assignee must be an active, non-deactivated user.
- Assignee must hold active membership in the project's parent team (cross-team assignment is rejected with 400).
- Passing `"assigned_to": null` safely unassigns the task.

---

## Audit Logging System

Every state-modifying action records an audit log entry within the same database transaction. If the primary mutation fails or raises an error, the transaction rolls back, guaranteeing zero orphan audit logs.

### Captured Action Types (17 Total)
- **User Actions**: `USER_REGISTERED`, `USER_UPDATED`, `USER_DEACTIVATED`
- **Team Actions**: `TEAM_CREATED`, `MEMBER_ADDED`, `MEMBER_REMOVED`, `MEMBER_ROLE_CHANGED`
- **Project Actions**: `PROJECT_CREATED`, `PROJECT_UPDATED`, `PROJECT_DELETED`
- **Task Actions**: `TASK_CREATED`, `TASK_UPDATED`, `TASK_COMPLETED`, `TASK_REOPENED`, `TASK_ASSIGNED`, `TASK_UNASSIGNED`, `TASK_DELETED`

### Security & Privacy
- Sensitive information (e.g. passwords, password hashes) is stripped before metadata serialization.
- `GET /audit-logs` enforces strict RBAC:
  - Standard users receive `403 Forbidden`.
  - Team Managers only see logs matching `team_id in (managed_teams)`.
  - Global Admins see the complete platform audit log.

---

## API Endpoint Directory

All 29 endpoints are grouped by functional area:

### 1. Authentication (`/auth`)
| Method | Endpoint | Description | Auth Required |
|---|---|---|:---:|
| `POST` | `/auth/register` | Register new user account (201 Created) | No |
| `POST` | `/auth/login` | Authenticate with email/password; returns JWT | No |
| `GET` | `/auth/me` | Return current authenticated user profile | Bearer |

### 2. Users (`/users`)
| Method | Endpoint | Description | Auth Required |
|---|---|---|:---:|
| `GET` | `/users/me` | Retrieve profile of the authenticated caller | Bearer |
| `PATCH` | `/users/me` | Update name or email (empty body is no-op) | Bearer |
| `POST` | `/users/me/deactivate` | Deactivate account (`is_active: false`) | Bearer |

### 3. Teams (`/teams`)
| Method | Endpoint | Description | Auth Required |
|---|---|---|:---:|
| `POST` | `/teams` | Create new team (caller becomes initial Manager) | Bearer |
| `GET` | `/teams` | List teams current user belongs to (with `user_role`) | Bearer |
| `GET` | `/teams/{team_id}` | Get team details | Member |
| `GET` | `/teams/{team_id}/members` | List members and roles in team | Member |
| `POST` | `/teams/{team_id}/members` | Add registered user to team | Manager |
| `DELETE` | `/teams/{team_id}/members/{user_id}` | Remove member (last-manager protected) | Manager |
| `PATCH` | `/teams/{team_id}/members/{user_id}` | Update member role (`MEMBER` <-> `MANAGER`) | Manager |

### 4. Projects (`/projects` & `/teams/{team_id}/projects`)
| Method | Endpoint | Description | Auth Required |
|---|---|---|:---:|
| `POST` | `/teams/{team_id}/projects` | Create project within team | Manager / Admin |
| `GET` | `/teams/{team_id}/projects` | List active projects in team | Member / Admin |
| `GET` | `/projects/{project_id}` | Get project details | Member / Admin |
| `PATCH` | `/projects/{project_id}` | Update project name or description | Manager / Admin |
| `DELETE` | `/projects/{project_id}` | Soft-delete project (requires `?confirm=true`) | Manager / Admin |

### 5. Tasks (`/tasks` & `/projects/{project_id}/tasks`)
| Method | Endpoint | Description | Auth Required |
|---|---|---|:---:|
| `POST` | `/tasks` | Create personal task | Bearer |
| `GET` | `/tasks` | List personal tasks (search, filter, sort, paginate) | Bearer (Owner) |
| `GET` | `/tasks/{task_id}` | Get task details | Owner / Member |
| `PATCH` | `/tasks/{task_id}` | Update task title, description, status, priority | Owner / Assignee / Manager |
| `PATCH` | `/tasks/{task_id}/assignment` | Assign or unassign task | Manager / Admin |
| `DELETE` | `/tasks/{task_id}` | Delete task | Owner / Manager / Admin |
| `POST` | `/projects/{project_id}/tasks` | Create project task | Manager / Admin |
| `GET` | `/projects/{project_id}/tasks` | List project tasks (search, filter, sort, paginate) | Member / Admin |

### 6. Audit Logs (`/audit-logs`)
| Method | Endpoint | Description | Auth Required |
|---|---|---|:---:|
| `GET` | `/audit-logs` | Query audit trail with multi-field filters & pagination | Manager / Admin |

### 7. Health (`/health`)
| Method | Endpoint | Description | Auth Required |
|---|---|---|:---:|
| `GET` | `/health` | API service liveness check | No |
| `GET` | `/health/db` | Database connectivity probe (`SELECT 1`) | No |

---

## Local Setup & Getting Started

### Prerequisites
- Python 3.11+
- Docker & Docker Compose
- Git

### Step-by-Step Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/your-username/Task-Management.git
   cd Task-Management
   ```

2. **Create and activate a virtual environment**:
   ```bash
   # Windows (PowerShell)
   python -m venv venv
   .\venv\Scripts\Activate.ps1

   # Linux / macOS
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Start PostgreSQL via Docker Compose**:
   ```bash
   docker-compose up -d db
   ```

5. **Configure environment variables**:
   ```bash
   cp .env.example .env
   ```
   *The default configuration in `.env.example` aligns with `docker-compose.yml`:*
   ```ini
   ENVIRONMENT=development
   DATABASE_URL=postgresql://task_user:task_password@localhost:5432/task_platform
   POSTGRES_USER=task_user
   POSTGRES_PASSWORD=task_password
   POSTGRES_DB=task_platform
   JWT_SECRET_KEY=supersecretkey_please_change_in_production
   JWT_ALGORITHM=HS256
   ACCESS_TOKEN_EXPIRE_MINUTES=60
   ```

---

## Database Migrations

Database schemas are managed using Alembic.

```bash
# Apply all pending migrations to the database
alembic upgrade head

# Roll back by one migration
alembic downgrade -1

# Create a new auto-generated migration (when models change)
alembic revision --autogenerate -m "describe_migration"
```

---

## Interactive API Docs & Swagger Workflow

Once the application is running, open your browser:
- **Swagger UI**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **ReDoc**: [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)

### Authenticating in Swagger UI

Because `/auth/login` expects a JSON body (rather than OAuth2 form data), authenticate using the following flow:

1. In Swagger UI, expand `POST /auth/register` and create an account.
2. Expand `POST /auth/login`, click **Try it out**, and provide your credentials:
   ```json
   {
     "email": "alice@example.com",
     "password": "password123"
   }
   ```
3. Click **Execute** and copy the `access_token` from the response body.
4. Click the green **Authorize** button at the top-right of Swagger UI.
5. In the value input, enter your token (e.g. `Bearer <paste-token-here>`) and click **Authorize**.
6. All protected routes will now execute with your authentication context.

---

## Testing & Quality Assurance

The test suite runs against an isolated, in-memory SQLite database (`conftest.py`) utilizing **function-scoped transaction rollback**. Every test begins with a clean slate without persisting data across runs or relying on test execution order.

### Running Tests

```bash
# Run the complete test suite quietly with short tracebacks
pytest -q --tb=short

# Run with full verbose output
pytest -v

# Run tests for a specific domain
pytest tests/test_tasks.py
pytest tests/test_audit_logs.py
pytest tests/test_task_sorting.py
```

### Verified Test Baseline
```
314 passed, 0 failed, 0 skipped
```

The 314 tests cover:
- Authentication & JWT handling (`test_auth.py`)
- User profiles & deactivation (`test_users.py`)
- Team management & last-manager rules (`test_teams.py`)
- Project management & soft deletion (`test_projects.py`)
- Task lifecycle & assignment validation (`test_tasks.py`)
- Task search, filtering, and pagination bounds (`test_task_queries.py`)
- Multi-field sorting & tie-breaking determinism (`test_task_sorting.py`)
- Transactional audit log recording & RBAC scoping (`test_audit_logs.py`)
- Edge cases, error contracts, and schema validation (`test_phase9.py`, `test_phase10.py`)
- Health probes and ORM definitions (`test_health.py`, `test_models.py`)

---

## Key Engineering Decisions

1. **Layered Architecture over Fat Controllers**: Routers remain thin (15–30 lines), delegating all validation, authorization, and data operations to `app/services/`.
2. **Transaction-Consistent Audit Trails**: Audit logging logic executes prior to `db.commit()`. If any step fails, the entire transaction rolls back, guaranteeing zero orphaned or phantom audit logs.
3. **Pydantic v2 Migration & Strict Models**: All schemas use `ConfigDict(from_attributes=True)` and `Field(..., min_length=1)` to disallow empty strings on critical entities while avoiding deprecated Pydantic v1 `class Config`.
4. **Deterministic Sorting**: Queries sorted by non-unique fields (e.g. `priority` or `due_date`) append a secondary tie-breaker (`Task.id.desc()`), ensuring stable pagination results across concurrent requests.
5. **Defensive Soft Deletion**: Projects cannot be deleted accidentally; the endpoint explicitly requires the caller to pass `?confirm=true`.
6. **Isolated Test Harness**: Tests use function-scoped SQLite savepoints and dependency overrides, avoiding flaky cross-test state leakage.

---

## Current Project Status

- **Phases 1–10**: Complete, verified, and locked.
- **Phase 11 (Documentation & DX)**: Complete.
- **Test Suite**: **314 passing tests (100% pass rate)**.
