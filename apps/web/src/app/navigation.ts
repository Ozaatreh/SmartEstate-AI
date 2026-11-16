import {
  Bell, Bot, Building2, CheckSquare, FileText, FolderKanban, LayoutGrid, Palette, ScrollText, Truck, Users, Wallet, type LucideIcon,
} from "lucide-react";

export interface NavItem {
  label: string;
  to: string;
  icon: LucideIcon;
  /** Hidden unless the user holds it (UI only — the API enforces). */
  permission?: string;
  /** Adds a live counter. */
  counter?: "notifications" | "approvals";
  end?: boolean;
}

export interface NavSection {
  label: string;
  items: NavItem[];
}

/**
 * Sidebar structure (UI_UX_DESIGN.md § 3). Only modules that exist are listed, so there are no dead
 * links — each phase adds its items here.
 */
export const NAVIGATION: NavSection[] = [
  {
    label: "Overview",
    items: [
      { label: "Home", to: "/", icon: LayoutGrid, end: true },
      { label: "Approvals", to: "/approvals", icon: CheckSquare, counter: "approvals" },
      { label: "Notifications", to: "/notifications", icon: Bell, counter: "notifications" },
    ],
  },
  {
    label: "Operations",
    items: [
      { label: "Purchase requests", to: "/procurement/requests", icon: FileText, permission: "procurement.requests.create" },
      { label: "Suppliers", to: "/procurement/suppliers", icon: Truck, permission: "procurement.suppliers.read" },
      { label: "Budgets", to: "/finance/budgets", icon: Wallet, permission: "finance.budgets.read" },
      { label: "Projects", to: "/finance/projects", icon: FolderKanban, permission: "finance.budgets.read" },
      { label: "Employees", to: "/hr/employees", icon: Users, permission: "hr.employees.read" },
      { label: "Departments", to: "/hr/departments", icon: Building2, permission: "hr.employees.read" },
      { label: "Automation", to: "/automation", icon: Bot, permission: "automation.workflows.read" },
    ],
  },
  {
    label: "Administration",
    items: [
      { label: "Audit log", to: "/admin/audit", icon: ScrollText, permission: "audit.logs.read" },
      { label: "Design system", to: "/_design", icon: Palette, permission: "system.design_reference.view" },
    ],
  },
];
