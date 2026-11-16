"""Imports every model module so Alembic autogenerate and tests see the full metadata."""

from app.modules.approvals.models import (  # noqa: F401
    ApprovalDecision,
    ApprovalPolicy,
    ApprovalPolicyStep,
    ApprovalRequest,
    ApprovalStep,
)
from app.modules.audit.models import AuditLog  # noqa: F401
from app.modules.finance.models import Budget, BudgetCategory, BudgetLedgerEntry, OperationalProject  # noqa: F401
from app.modules.hr.models import Department, Employee  # noqa: F401
from app.modules.identity.models import Permission, Role, RolePermission, User, UserRole  # noqa: F401
from app.modules.notifications.models import Notification  # noqa: F401
from app.modules.procurement.models import (  # noqa: F401
    PurchaseRequest,
    PurchaseRequestItem,
    QuotationItem,
    Supplier,
    SupplierQuotation,
)
