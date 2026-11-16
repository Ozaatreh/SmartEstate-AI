import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { NavLink, useMatch } from "react-router-dom";
import { NAVIGATION, type NavItem } from "@/app/navigation";
import { Wordmark } from "@/components/system/brand";
import { Tooltip } from "@/components/ui/primitives";
import { useAuth } from "@/features/auth/auth-context";
import { usePendingApprovals } from "@/features/approvals/api";
import { useUnreadCount } from "@/features/platform/api";
import { cn } from "@/lib/utils";

export function SidebarNav({ collapsed, onNavigate }: { collapsed: boolean; onNavigate?: () => void }) {
  const { can } = useAuth();
  const unread = useUnreadCount();
  const approvals = usePendingApprovals();
  const counters = { notifications: unread.data?.unread, approvals: approvals.data?.pending };
  const sections = NAVIGATION.map((s) => ({ ...s, items: s.items.filter((i) => !i.permission || can(i.permission)) })).filter((s) => s.items.length);

  return (
    <nav aria-label="Main" className="flex-1 overflow-y-auto px-3 py-3">
      {sections.map((section) => (
        <div key={section.label} className="mb-5 last:mb-0">
          {collapsed ? (
            <div className="mx-auto mb-2 h-px w-6 bg-border" aria-hidden />
          ) : (
            <p className="mb-1 px-2 text-caption font-medium uppercase tracking-[0.06em] text-fg-muted">{section.label}</p>
          )}
          <ul className="space-y-0.5">
            {section.items.map((item) => (
              <li key={item.to}>
                <SidebarLink item={item} collapsed={collapsed} onNavigate={onNavigate}
                  count={item.counter ? counters[item.counter] : undefined} />
              </li>
            ))}
          </ul>
        </div>
      ))}
    </nav>
  );
}

function SidebarLink({ item, collapsed, count, onNavigate }: { item: NavItem; collapsed: boolean; count?: number; onNavigate?: () => void }) {
  const Icon = item.icon;
  // Active state is resolved here (not via NavLink's className function) because Radix's
  // Slot, used by the collapsed-mode tooltip, can only merge string class names.
  const isActive = Boolean(useMatch({ path: item.to, end: item.end ?? false }));
  const link = (
    <NavLink
      to={item.to}
      end={item.end}
      onClick={onNavigate}
      aria-label={collapsed ? item.label : undefined}
      className={cn(
        "relative flex h-8 items-center gap-2.5 rounded-[var(--radius-control)] text-body font-medium transition-colors duration-150",
        collapsed ? "justify-center px-0" : "px-2",
        isActive ? "bg-surface text-fg shadow-[inset_0_0_0_1px_var(--border)]" : "text-fg-secondary hover:bg-surface-sunken hover:text-fg",
      )}
    >
      {isActive && <span aria-hidden className="absolute -left-3 top-1.5 h-5 w-0.5 rounded-r bg-brand" />}
      <Icon className={cn("size-[18px] shrink-0", isActive ? "text-brand" : "text-fg-muted")} strokeWidth={1.75} />
      {!collapsed && <span className="truncate">{item.label}</span>}
      {count ? (
        collapsed ? (
          <span className="absolute right-1.5 top-1 size-2 rounded-full bg-brand" aria-label={`${count} unread`} />
        ) : (
          <span className="tabular ml-auto rounded-full bg-brand-subtle px-1.5 text-caption font-semibold text-brand">{count > 99 ? "99+" : count}</span>
        )
      ) : null}
    </NavLink>
  );
  return collapsed ? <Tooltip content={item.label} side="right">{link}</Tooltip> : link;
}

export function DesktopSidebar({ collapsed, onToggle }: { collapsed: boolean; onToggle: () => void }) {
  return (
    <aside
      className={cn(
        "sticky top-0 hidden h-dvh shrink-0 flex-col border-r border-border bg-surface-subtle transition-[width] duration-200 ease-[var(--ease-standard)] md:flex",
        collapsed ? "w-[var(--sidebar-rail)]" : "w-[var(--sidebar-width)]",
      )}
    >
      <div className={cn("flex h-[var(--topbar-height)] shrink-0 items-center border-b border-border", collapsed ? "justify-center" : "px-4")}>
        <NavLink to="/" aria-label="SmartEstate AI home"><Wordmark collapsed={collapsed} /></NavLink>
      </div>
      <SidebarNav collapsed={collapsed} />
      <div className={cn("shrink-0 border-t border-border p-3", collapsed && "flex justify-center")}>
        <Tooltip content={collapsed ? "Expand sidebar  [" : "Collapse sidebar  ["} side="right">
          <button type="button" onClick={onToggle} aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"} aria-expanded={!collapsed}
            className={cn("flex h-8 items-center gap-2.5 rounded-[var(--radius-control)] text-body text-fg-muted transition-colors hover:bg-surface-sunken hover:text-fg",
              collapsed ? "w-8 justify-center" : "w-full px-2")}>
            {collapsed ? <PanelLeftOpen className="size-[18px]" /> : <><PanelLeftClose className="size-[18px]" /><span>Collapse</span></>}
          </button>
        </Tooltip>
      </div>
    </aside>
  );
}
