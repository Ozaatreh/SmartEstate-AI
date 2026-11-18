"""Imports every model module so Alembic autogenerate and tests see the full metadata."""

from app.ai.models import AIConversation, AIMessage, AIToolCall, AIUsage  # noqa: F401
from app.automation.models import (  # noqa: F401
    AutomationEvent,
    WorkerHeartbeat,
    WorkflowDefinition,
    WorkflowExecution,
    WorkflowExecutionLog,
    WorkflowStepExecution,
)
from app.modules.approvals.models import (  # noqa: F401
    ApprovalDecision,
    ApprovalPolicy,
    ApprovalPolicyStep,
    ApprovalRequest,
    ApprovalStep,
)
from app.modules.audit.models import AuditLog  # noqa: F401
from app.modules.crm.models import Lead, LeadActivity, SalesAssignmentState, UnitReservation  # noqa: F401
from app.modules.finance.models import Budget, BudgetCategory, BudgetLedgerEntry, OperationalProject  # noqa: F401
from app.modules.hr.models import Department, Employee  # noqa: F401
from app.modules.identity.models import Permission, Role, RolePermission, User, UserRole  # noqa: F401
from app.modules.marketing.models import MarketingCampaign, MarketingContent, MarketingContentVersion  # noqa: F401
from app.modules.notifications.models import Notification  # noqa: F401
from app.modules.procurement.models import (  # noqa: F401
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseRequest,
    PurchaseRequestItem,
    QuotationItem,
    Supplier,
    SupplierQuotation,
)
from app.modules.realestate.model3d.models import RePropertyModel  # noqa: F401
from app.modules.realestate.models import ReBuilding, RePaymentPlan, ReProject, ReUnit  # noqa: F401
