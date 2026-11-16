"""The permission catalogue — the single place permission codes are declared.

Codes are ``<module>.<resource>.<action>``. Code checks permissions, never role names; the only
special role is Super Admin, which implicitly holds every permission.

When a phase introduces a permission, ``python -m app.seed`` creates it and grants it **once** to
the default roles listed here. Grants edited later by administrators are never overwritten.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Perm(StrEnum):
    # Platform
    AUDIT_LOGS_READ = "audit.logs.read"
    IDENTITY_USERS_READ = "identity.users.read"
    IDENTITY_USERS_MANAGE = "identity.users.manage"
    IDENTITY_ROLES_MANAGE = "identity.roles.manage"
    SYSTEM_DESIGN_REFERENCE = "system.design_reference.view"
    # HR
    HR_EMPLOYEES_READ = "hr.employees.read"
    HR_EMPLOYEES_MANAGE = "hr.employees.manage"
    HR_DEPARTMENTS_MANAGE = "hr.departments.manage"
    # Finance
    FINANCE_BUDGETS_READ = "finance.budgets.read"
    FINANCE_BUDGETS_MANAGE = "finance.budgets.manage"
    FINANCE_PROJECTS_MANAGE = "finance.projects.manage"
    # Procurement
    PROCUREMENT_SUPPLIERS_READ = "procurement.suppliers.read"
    PROCUREMENT_SUPPLIERS_MANAGE = "procurement.suppliers.manage"
    PROCUREMENT_REQUESTS_CREATE = "procurement.requests.create"
    PROCUREMENT_REQUESTS_READ_ALL = "procurement.requests.read_all"
    PROCUREMENT_QUOTATIONS_MANAGE = "procurement.quotations.manage"
    # Approvals (one permission per approval level; the department level is normally assigned to the manager)
    APPROVALS_DEPARTMENT = "approvals.department.approve"
    APPROVALS_FINANCE = "approvals.finance.approve"
    APPROVALS_EXECUTIVE = "approvals.executive.approve"
    APPROVALS_READ_ALL = "approvals.requests.read_all"


PERMISSION_DESCRIPTIONS: dict[Perm, str] = {
    Perm.AUDIT_LOGS_READ: "View the audit log",
    Perm.IDENTITY_USERS_READ: "View users",
    Perm.IDENTITY_USERS_MANAGE: "Create, edit and deactivate users",
    Perm.IDENTITY_ROLES_MANAGE: "Create roles and edit their permissions",
    Perm.SYSTEM_DESIGN_REFERENCE: "View the design-system reference page",
    Perm.HR_EMPLOYEES_READ: "View the employee directory and profiles",
    Perm.HR_EMPLOYEES_MANAGE: "Create and edit employees and reporting lines",
    Perm.HR_DEPARTMENTS_MANAGE: "Create and edit departments and their managers",
    Perm.FINANCE_BUDGETS_READ: "View budgets, positions and the budget ledger",
    Perm.FINANCE_BUDGETS_MANAGE: "Create budgets and change allocations",
    Perm.FINANCE_PROJECTS_MANAGE: "Create and edit operational projects",
    Perm.PROCUREMENT_SUPPLIERS_READ: "View suppliers",
    Perm.PROCUREMENT_SUPPLIERS_MANAGE: "Create and edit suppliers",
    Perm.PROCUREMENT_REQUESTS_CREATE: "Create and submit own purchase requests",
    Perm.PROCUREMENT_REQUESTS_READ_ALL: "View every purchase request",
    Perm.PROCUREMENT_QUOTATIONS_MANAGE: "Record supplier quotations, select a supplier and send requests for approval",
    Perm.APPROVALS_DEPARTMENT: "Approve at department level when no department manager is available",
    Perm.APPROVALS_FINANCE: "Approve at finance level",
    Perm.APPROVALS_EXECUTIVE: "Approve at executive level",
    Perm.APPROVALS_READ_ALL: "View every approval request",
}

SUPER_ADMIN_ROLE = "super_admin"


@dataclass(frozen=True)
class RoleSpec:
    code: str
    name: str
    description: str
    permissions: frozenset[Perm]


P = Perm
_STAFF = {P.HR_EMPLOYEES_READ, P.PROCUREMENT_REQUESTS_CREATE}

# Default roles (data; editable later).
DEFAULT_ROLES: tuple[RoleSpec, ...] = (
    RoleSpec(SUPER_ADMIN_ROLE, "Super Admin", "Full access to every module and setting", frozenset(Perm)),
    RoleSpec("executive", "Executive", "Company-wide visibility and top-tier approvals", frozenset({
        *_STAFF, P.AUDIT_LOGS_READ, P.FINANCE_BUDGETS_READ, P.PROCUREMENT_SUPPLIERS_READ, P.PROCUREMENT_REQUESTS_READ_ALL,
        P.APPROVALS_EXECUTIVE, P.APPROVALS_READ_ALL,
    })),
    RoleSpec("finance_manager", "Finance Manager", "Budgets, expenses and financial approvals", frozenset({
        *_STAFF, P.FINANCE_BUDGETS_READ, P.FINANCE_BUDGETS_MANAGE, P.FINANCE_PROJECTS_MANAGE, P.PROCUREMENT_SUPPLIERS_READ,
        P.PROCUREMENT_REQUESTS_READ_ALL, P.APPROVALS_FINANCE, P.APPROVALS_READ_ALL,
    })),
    RoleSpec("hr_manager", "HR Manager", "Employees, departments and leave", frozenset({
        *_STAFF, P.IDENTITY_USERS_READ, P.HR_EMPLOYEES_MANAGE, P.HR_DEPARTMENTS_MANAGE,
    })),
    RoleSpec("department_manager", "Department Manager", "First-level approvals for a department", frozenset({
        *_STAFF, P.FINANCE_BUDGETS_READ, P.PROCUREMENT_SUPPLIERS_READ,
    })),
    RoleSpec("procurement_officer", "Procurement Officer", "Suppliers, purchase requests and orders", frozenset({
        *_STAFF, P.FINANCE_BUDGETS_READ, P.PROCUREMENT_SUPPLIERS_READ, P.PROCUREMENT_SUPPLIERS_MANAGE,
        P.PROCUREMENT_REQUESTS_READ_ALL, P.PROCUREMENT_QUOTATIONS_MANAGE,
    })),
    RoleSpec("sales_manager", "Sales Manager", "Leads, assignment, escalations and reservations", frozenset(_STAFF)),
    RoleSpec("sales_agent", "Sales Agent", "Own leads, activities and reservations", frozenset(_STAFF)),
    RoleSpec("marketing_manager", "Marketing Manager", "Campaigns and AI content approval", frozenset(_STAFF)),
    RoleSpec("employee", "Employee", "Own profile and own requests", frozenset(_STAFF)),
)

ALL_PERMISSIONS: frozenset[str] = frozenset(p.value for p in Perm)
