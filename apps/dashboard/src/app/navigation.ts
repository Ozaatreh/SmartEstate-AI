import {
  Bell, Bot, Building, Building2, CalendarCheck, CheckSquare, ClipboardCheck, Contact, DoorOpen, FileImage, FileText, FolderKanban, LayoutGrid, Megaphone, Palette, PenLine, ScrollText, Sparkles, Truck, Users, Wallet, type LucideIcon,
} from "lucide-react";

export interface NavItem {
  label: string;
  to: string;
  icon: LucideIcon;
  /** Hidden unless the user holds it (UI only — the API enforces). */
  permission?: string;
  /** Hidden unless the user holds at least one of these. */
  anyOf?: string[];
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
    label: "Sales",
    items: [
      { label: "Leads", to: "/crm/leads", icon: Contact, anyOf: ["crm.leads.create", "crm.leads.work", "crm.leads.read_all"] },
      { label: "Reservations", to: "/crm/reservations", icon: CalendarCheck, anyOf: ["crm.reservations.manage", "crm.leads.read_all"] },
    ],
  },
  {
    label: "Real estate",
    items: [
      { label: "Property Portfolio", to: "/realestate/projects", icon: Building, permission: "realestate.inventory.read" },
      { label: "Units", to: "/realestate/units", icon: DoorOpen, permission: "realestate.inventory.read" },
    ],
  },
  {
    label: "Operations",
    items: [
      { label: "Purchase requests", to: "/procurement/requests", icon: FileText, permission: "procurement.requests.create" },
      { label: "Purchase orders", to: "/procurement/orders", icon: ClipboardCheck, permission: "procurement.requests.create" },
      { label: "Suppliers", to: "/procurement/suppliers", icon: Truck, permission: "procurement.suppliers.read" },
      { label: "Budgets", to: "/finance/budgets", icon: Wallet, permission: "finance.budgets.read" },
      { label: "Operational Projects", to: "/finance/projects", icon: FolderKanban, permission: "finance.budgets.read" },
      { label: "Employees", to: "/hr/employees", icon: Users, permission: "hr.employees.read" },
      { label: "Departments", to: "/hr/departments", icon: Building2, permission: "hr.employees.read" },
      { label: "Automation", to: "/automation", icon: Bot, permission: "automation.workflows.read" },
    ],
  },
  {
    label: "Marketing",
    items: [
      { label: "Campaigns", to: "/marketing/campaigns", icon: Megaphone, permission: "marketing.campaigns.read" },
      { label: "Content", to: "/marketing/content", icon: PenLine, permission: "marketing.campaigns.read" },
      { label: "Brochures & posters", to: "/marketing/collateral", icon: FileImage, permission: "marketing.collateral.generate" },
    ],
  },
  {
    label: "Intelligence",
    items: [
      { label: "BI Agent", to: "/intelligence/bi-agent", icon: Sparkles, permission: "ai.bi_agent.use" },
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
