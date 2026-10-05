from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.api.endpoints import health, auth, users, teams, projects, tasks, audit_logs
from app.core.logger import logger

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up Task Management API...")
    yield
    logger.info("Shutting down Task Management API...")

API_DESCRIPTION = """
A clean, modular REST API for task management and team collaboration built with FastAPI, SQLAlchemy, and PostgreSQL.

### Core Capabilities
- **Authentication**: JWT-based stateless authentication with password hashing (bcrypt) and email normalization.
- **Role-Based Access Control (RBAC)**: Dual-tier authorization with Global Roles (`USER`, `ADMIN`) and Team Roles (`MEMBER`, `MANAGER`).
- **Teams & Membership**: Multi-tenant team structures with manager-only management and last-manager demotion/removal protection.
- **Projects**: Scoped workspaces within teams with soft-deletion confirmation guards and global admin bypass.
- **Tasks**: Personal (private) tasks and project-scoped tasks, assignment lifecycle, state transitions (`TODO` -> `IN_PROGRESS` -> `COMPLETED`), and automated completion timestamp tracking.
- **Search, Filtering, Sorting & Pagination**: Case-insensitive text search, multi-criteria filtering, tie-breaker deterministic sorting, and standardized pagination across tasks.
- **Audit Logging**: Comprehensive, transaction-consistent audit trail capturing all 17 mutation actions with team-scoped access control.

### Swagger UI Authentication Workflow
1. Execute `POST /auth/login` with your credentials in the JSON request body:
   ```json
   {
     "email": "user@example.com",
     "password": "yourpassword"
   }
   ```
2. Copy the returned `access_token`.
3. Click the green **Authorize** button at the top-right of this page.
4. Enter the token in the value input field (format: `Bearer <token>` or plain token) and click **Authorize**.
5. All protected endpoints will now include the Bearer token in request headers.
"""

TAGS_METADATA = [
    {
        "name": "Health",
        "description": "API liveness probes and database connectivity health checks.",
    },
    {
        "name": "Authentication",
        "description": "User registration, authentication, JWT token issuance, and authenticated identity verification.",
    },
    {
        "name": "Users",
        "description": "User profile management and account deactivation.",
    },
    {
        "name": "Teams",
        "description": "Team creation, membership roster management, and member role assignment.",
    },
    {
        "name": "Projects",
        "description": "Team-scoped project management with access control and soft-deletion protection.",
    },
    {
        "name": "Tasks",
        "description": "Personal and project task lifecycle, assignment, search, filtering, pagination, and sorting.",
    },
    {
        "name": "Audit Logs",
        "description": "Transaction-consistent audit trail recording all platform state mutations with RBAC scoping.",
    },
]

app = FastAPI(
    title="Task Management API",
    description=API_DESCRIPTION,
    version="1.0.0",
    openapi_tags=TAGS_METADATA,
    lifespan=lifespan,
)

app.include_router(health.router, tags=["Health"])
app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(users.router, prefix="/users", tags=["Users"])
app.include_router(teams.router, prefix="/teams", tags=["Teams"])
app.include_router(projects.router, tags=["Projects"])
app.include_router(tasks.router, tags=["Tasks"])
app.include_router(audit_logs.router, tags=["Audit Logs"])
