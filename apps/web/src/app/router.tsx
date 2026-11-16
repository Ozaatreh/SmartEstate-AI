import * as React from "react";
import { createBrowserRouter, Outlet } from "react-router-dom";
import { AppShell } from "@/components/layout/app-shell";
import { TableSkeleton } from "@/components/system/states";
import { Skeleton } from "@/components/ui/primitives";
import { AuthProvider, RequireAuth, RequirePermission } from "@/features/auth/auth-context";
import { NotFoundPage, RouteErrorPage } from "@/features/errors/error-pages";

const SignInPage = React.lazy(() => import("@/features/auth/sign-in-page"));
const HomePage = React.lazy(() => import("@/features/home/home-page"));
const NotificationsPage = React.lazy(() => import("@/features/notifications/notifications-page"));
const AuditPage = React.lazy(() => import("@/features/audit/audit-page"));
const DesignReferencePage = React.lazy(() => import("@/features/design/design-reference-page"));
const EmployeesPage = React.lazy(() => import("@/features/hr/employees-page"));
const EmployeeProfilePage = React.lazy(() => import("@/features/hr/employee-profile-page"));
const DepartmentsPage = React.lazy(() => import("@/features/hr/departments-page"));
const BudgetsPage = React.lazy(() => import("@/features/finance/budgets-page"));
const BudgetDetailPage = React.lazy(() => import("@/features/finance/budget-detail-page"));
const ProjectsPage = React.lazy(() => import("@/features/finance/projects-page"));
const RequestsPage = React.lazy(() => import("@/features/procurement/requests-page"));
const RequestFormPage = React.lazy(() => import("@/features/procurement/request-form-page"));
const RequestDetailPage = React.lazy(() => import("@/features/procurement/request-detail-page"));
const SuppliersPage = React.lazy(() => import("@/features/procurement/suppliers-page"));
const ApprovalsPage = React.lazy(() => import("@/features/approvals/approvals-page"));
const AutomationPage = React.lazy(() => import("@/features/automation/automation-page"));
const WorkflowDetailPage = React.lazy(() => import("@/features/automation/workflow-detail-page"));
const ExecutionsPage = React.lazy(() => import("@/features/automation/executions-page"));
const ExecutionDetailPage = React.lazy(() => import("@/features/automation/execution-detail-page"));

function PageFallback() {
  return (
    <div aria-busy="true" aria-label="Loading page">
      <Skeleton className="mb-2 h-7 w-56" />
      <Skeleton className="mb-8 h-4 w-80" />
      <div className="rounded-[var(--radius-panel)] border border-border bg-surface"><TableSkeleton /></div>
    </div>
  );
}

const page = (el: React.ReactNode) => <React.Suspense fallback={<PageFallback />}>{el}</React.Suspense>;
const guarded = (permission: string, el: React.ReactNode) => <RequirePermission permission={permission}>{page(el)}</RequirePermission>;

function Root() {
  return <AuthProvider><Outlet /></AuthProvider>;
}

export const router = createBrowserRouter([
  {
    element: <Root />,
    errorElement: <RouteErrorPage />,
    children: [
      { path: "/sign-in", element: <React.Suspense fallback={null}><SignInPage /></React.Suspense> },
      {
        element: <RequireAuth />,
        children: [
          {
            element: <AppShell />,
            children: [
              { index: true, element: page(<HomePage />), handle: { title: "Home" } },
              { path: "notifications", element: page(<NotificationsPage />), handle: { title: "Notifications" } },
              { path: "approvals", element: page(<ApprovalsPage />), handle: { title: "Approvals" } },
              { path: "automation", element: guarded("automation.workflows.read", <AutomationPage />), handle: { section: "Automation", title: "Workflows" } },
              { path: "automation/workflows/:key", element: guarded("automation.workflows.read", <WorkflowDetailPage />), handle: { section: "Automation", title: "Workflow" } },
              { path: "automation/executions", element: guarded("automation.workflows.read", <ExecutionsPage />), handle: { section: "Automation", title: "Executions" } },
              { path: "automation/executions/:id", element: guarded("automation.workflows.read", <ExecutionDetailPage />), handle: { section: "Automation", title: "Execution" } },
              { path: "procurement/requests", element: guarded("procurement.requests.create", <RequestsPage />), handle: { section: "Procurement", title: "Purchase requests" } },
              { path: "procurement/requests/new", element: guarded("procurement.requests.create", <RequestFormPage />), handle: { section: "Procurement", title: "New request" } },
              { path: "procurement/requests/:id", element: page(<RequestDetailPage />), handle: { section: "Procurement", title: "Purchase request" } },
              { path: "procurement/requests/:id/edit", element: guarded("procurement.requests.create", <RequestFormPage />), handle: { section: "Procurement", title: "Edit request" } },
              { path: "procurement/suppliers", element: guarded("procurement.suppliers.read", <SuppliersPage />), handle: { section: "Procurement", title: "Suppliers" } },
              { path: "finance/budgets", element: guarded("finance.budgets.read", <BudgetsPage />), handle: { section: "Finance", title: "Budgets" } },
              { path: "finance/budgets/:id", element: guarded("finance.budgets.read", <BudgetDetailPage />), handle: { section: "Finance", title: "Budget" } },
              { path: "finance/projects", element: guarded("finance.budgets.read", <ProjectsPage />), handle: { section: "Finance", title: "Projects" } },
              { path: "hr/employees", element: guarded("hr.employees.read", <EmployeesPage />), handle: { section: "People", title: "Employees" } },
              { path: "hr/employees/:id", element: guarded("hr.employees.read", <EmployeeProfilePage />), handle: { section: "People", title: "Employee" } },
              { path: "hr/departments", element: guarded("hr.employees.read", <DepartmentsPage />), handle: { section: "People", title: "Departments" } },
              { path: "admin/audit", element: guarded("audit.logs.read", <AuditPage />), handle: { section: "Administration", title: "Audit log" } },
              { path: "_design", element: guarded("system.design_reference.view", <DesignReferencePage />), handle: { section: "Administration", title: "Design system" } },
              { path: "*", element: <NotFoundPage />, handle: { title: "Not found" } },
            ],
          },
        ],
      },
    ],
  },
]);
