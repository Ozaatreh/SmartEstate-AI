import { AtSign, Briefcase, Camera, Globe, Mail, MessageCircle, type LucideIcon } from "lucide-react";
import { Badge, StatusBadge } from "@/components/system/badges";
import { cn } from "@/lib/utils";
import type { Channel, ContentStatus } from "./api";
import { CHANNELS, CONTENT_STATUS_LABEL } from "./logic";

const ICONS: Record<Channel, LucideIcon> = { instagram: Camera, x: AtSign, linkedin: Briefcase, email: Mail, website: Globe, whatsapp: MessageCircle };

export function ChannelLabel({ channel, className }: { channel: Channel; className?: string }) {
  const Icon = ICONS[channel];
  return <span className={cn("inline-flex items-center gap-1.5 text-small", className)}><Icon className="size-3.5 text-fg-muted" aria-hidden />{CHANNELS[channel].label}</span>;
}

export function LanguageBadge({ language }: { language: string }) {
  return <Badge tone="neutral" dot={false}>{language === "ar" ? "العربية · AR" : "English · EN"}</Badge>;
}

export function ContentStatusBadge({ status }: { status: ContentStatus }) {
  return <StatusBadge status={status === "rejected" ? "rejected" : status} label={CONTENT_STATUS_LABEL[status]} />;
}
