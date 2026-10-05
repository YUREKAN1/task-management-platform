import enum

class GlobalRole(str, enum.Enum):
    USER = "USER"
    MANAGER = "MANAGER"
    ADMIN = "ADMIN"

class TeamRole(str, enum.Enum):
    MEMBER = "MEMBER"
    MANAGER = "MANAGER"

class TaskStatus(str, enum.Enum):
    TODO = "TODO"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"

class TaskPriority(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"

class AuditAction(str, enum.Enum):
    # User actions
    USER_REGISTERED = "USER_REGISTERED"
    USER_UPDATED = "USER_UPDATED"
    USER_DEACTIVATED = "USER_DEACTIVATED"

    # Team actions
    TEAM_CREATED = "TEAM_CREATED"
    MEMBER_ADDED = "MEMBER_ADDED"
    MEMBER_REMOVED = "MEMBER_REMOVED"
    MEMBER_ROLE_CHANGED = "MEMBER_ROLE_CHANGED"

    # Project actions
    PROJECT_CREATED = "PROJECT_CREATED"
    PROJECT_UPDATED = "PROJECT_UPDATED"
    PROJECT_DELETED = "PROJECT_DELETED"

    # Task actions
    TASK_CREATED = "TASK_CREATED"
    TASK_UPDATED = "TASK_UPDATED"
    TASK_COMPLETED = "TASK_COMPLETED"
    TASK_REOPENED = "TASK_REOPENED"
    TASK_ASSIGNED = "TASK_ASSIGNED"
    TASK_UNASSIGNED = "TASK_UNASSIGNED"
    TASK_DELETED = "TASK_DELETED"

class AuditEntityType(str, enum.Enum):
    USER = "user"
    TEAM = "team"
    PROJECT = "project"
    TASK = "task"
