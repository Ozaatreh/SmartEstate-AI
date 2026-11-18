import { Bell, CheckCheck, LogOut, Menu, MoonStar, Sun, UserRound } from "lucide-react";
import * as React from "react";
import { Link, useMatches, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Badge } from "@/components/system/badges";
import { ListSkeleton } from "@/components/system/states";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/menu";
import { Avatar, Popover, PopoverContent, PopoverTrigger } from "@/components/ui/primitives";
import { useLogout } from "@/features/auth/api";
import { useAuth } from "@/features/auth/auth-context";
import { useMarkAllRead, useMarkRead, useNotifications, useUnreadCount, type Notification } from "@/features/platform/api";
import { formatRelative } from "@/lib/format";
import { useTheme } from "@/lib/theme";
import { cn } from "@/lib/utils";

interface RouteHandle { title?: string; section?: string }

export function TopBar({ onOpenMobileNav }: { onOpenMobileNav: () => void }) {
  const matches = useMatches();
  const handle = [...matches].reverse().find((m) => (m.handle as RouteHandle | undefined)?.title)?.handle as RouteHandle | undefined;

  return (
    <header className="sticky top-0 z-30 flex h-[var(--topbar-height)] shrink-0 items-center gap-3 border-b border-border bg-canvas/90 px-4 backdrop-blur-sm sm:px-6">
      <Button size="icon" variant="ghost" className="md:hidden" onClick={onOpenMobileNav} aria-label="Open navigation"><Menu /></Button>
      <div className="flex min-w-0 items-center gap-1.5 text-body">
        {handle?.section && <><span className="hidden text-fg-muted sm:inline">{handle.section}</span><span className="hidden text-fg-muted sm:inline">/</span></>}
        <span className="truncate font-medium text-fg">{handle?.title ?? "SmartEstate AI"}</span>
      </div>
      <div className="ml-auto flex items-center gap-1">
        <ThemeToggle />
        <NotificationsPopover />
        <UserMenu />
      </div>
    </header>
  );
}

/** Light / dark theme for the whole app; remembered on this device, following the system setting until changed. */
export function ThemeToggle() {
  const { theme, toggle } = useTheme();
  const dark = theme === "dark";
  return (
    <Button size="icon" variant="ghost" onClick={toggle} aria-pressed={dark} title={dark ? "Light theme" : "Dark theme"}
      aria-label={dark ? "Switch to light theme" : "Switch to dark theme"}>
      {dark ? <Sun /> : <MoonStar />}
    </Button>
  );
}

function NotificationsPopover() {
  const [open, setOpen] = React.useState(false);
  const unread = useUnreadCount();
  const list = useNotifications({ page_size: 6 });
  const markAll = useMarkAllRead();
  const markRead = useMarkRead();
  const count = unread.data?.unread ?? 0;
  const navigate = useNavigate();

  const openItem = (n: Notification) => {
    if (!n.read_at) markRead.mutate(n.id);
    setOpen(false);
    if (n.link) navigate(n.link);
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button size="icon" variant="ghost" aria-label={count ? `Notifications, ${count} unread` : "Notifications"} className="relative">
          <Bell />
          {count > 0 && <span className="absolute right-1.5 top-1.5 size-2 rounded-full bg-brand ring-2 ring-canvas" />}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[min(380px,calc(100vw-2rem))] p-0">
        <div className="flex items-center justify-between border-b border-border-subtle px-4 py-3">
          <p className="text-body font-semibold">Notifications</p>
          <Button size="sm" variant="ghost" disabled={!count} loading={markAll.isPending}
            onClick={() => markAll.mutate(undefined, { onSuccess: () => toast.success("All notifications marked as read") })}>
            <CheckCheck /> Mark all read
          </Button>
        </div>
        <div className="max-h-[360px] overflow-y-auto">
          {list.isPending ? <ListSkeleton rows={3} /> : !list.data?.items.length ? (
            <p className="px-4 py-10 text-center text-body text-fg-muted">You're all caught up.</p>
          ) : (
            <ul className="divide-y divide-border-subtle">
              {list.data.items.map((n) => (
                <li key={n.id}>
                  <button type="button" onClick={() => openItem(n)} className="flex w-full gap-3 px-4 py-3 text-left transition-colors hover:bg-surface-subtle">
                    <span className={cn("mt-1.5 size-2 shrink-0 rounded-full", n.read_at ? "bg-transparent" : "bg-brand")} aria-label={n.read_at ? undefined : "Unread"} />
                    <span className="min-w-0 flex-1">
                      <span className={cn("block text-body", n.read_at ? "text-fg-secondary" : "font-medium text-fg")}>{n.title}</span>
                      {n.body && <span className="mt-0.5 line-clamp-2 block text-small text-fg-muted">{n.body}</span>}
                      <span className="mt-1 block text-caption text-fg-muted">{formatRelative(n.created_at)}</span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="border-t border-border-subtle px-4 py-2">
          <Link to="/notifications" onClick={() => setOpen(false)} className="text-small font-medium text-brand hover:underline">View all notifications</Link>
        </div>
      </PopoverContent>
    </Popover>
  );
}

function UserMenu() {
  const { user } = useAuth();
  const logout = useLogout();
  const navigate = useNavigate();
  if (!user) return null;

  const signOut = () => logout.mutate(undefined, {
    onSettled: () => {
      navigate("/sign-in", { replace: true });
      toast.success("You've been signed out");
    },
  });

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button type="button" aria-label="Account menu" className="ml-1 flex items-center gap-2 rounded-full p-0.5 transition-colors hover:bg-surface-sunken sm:rounded-[var(--radius-control)] sm:py-1 sm:pl-1 sm:pr-2">
          <Avatar initials={user.initials} />
          <span className="hidden text-left leading-tight lg:block">
            <span className="block text-small font-medium text-fg">{user.full_name}</span>
            <span className="block text-caption text-fg-muted">{user.roles[0]?.name ?? "No role"}</span>
          </span>
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent className="w-64">
        <div className="px-2 py-2">
          <p className="text-body font-medium">{user.full_name}</p>
          <p className="truncate text-small text-fg-muted">{user.email}</p>
          <div className="mt-2 flex flex-wrap gap-1">{user.roles.map((r) => <Badge key={r.code} tone="neutral" dot={false}>{r.name}</Badge>)}</div>
        </div>
        <DropdownMenuSeparator />
        <DropdownMenuLabel>Account</DropdownMenuLabel>
        <DropdownMenuItem onSelect={() => navigate("/")}><UserRound /> My workspace</DropdownMenuItem>
        <DropdownMenuItem tone="danger" onSelect={signOut} disabled={logout.isPending}><LogOut /> Sign out</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
