"""Action Registry modules. Importing this package registers every action."""

# Approval subjects register on import; reminders/escalations in the worker need every subject's adapter.
import app.modules.marketing.service  # noqa: E402, F401
from app.automation.actions import approvals, crm, finance, procurement  # noqa: F401
