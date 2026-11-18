import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, apiUpload, type ListQuery, type Page } from "@/lib/api-client";

export type UnitStatus = "available" | "reserved" | "sold" | "blocked";
export interface StatusCounts { available: number; reserved: number; sold: number; blocked: number; total: number }
export interface ProjectRef { id: string; code: string; name: string }
/** A project media entry: a web link (`url`) or a local approved image (`file`, used by brochures/posters only). */
/** Upload limits mirrored from the API (it re-checks the file's real type and size). */
export const IMAGE_UPLOAD = { types: ["image/jpeg", "image/png", "image/webp"], accept: ".jpg,.jpeg,.png,.webp", maxBytes: 10 * 1024 * 1024 };

export interface UploadedImage { file: string; id: string; size_bytes: number }

/** Stores an image for the project; it becomes part of the project when the media list is saved with it. */
export const uploadProjectImage = (projectId: string, file: File) =>
  apiUpload<UploadedImage>(`/realestate/projects/${projectId}/media/images`, file);

/** Staff preview URL of one of the project's uploaded images. */
export const projectImageUrl = (projectId: string, file: string) =>
  `/api/v1/realestate/projects/${projectId}/media/file?file=${encodeURIComponent(file)}`;

export interface MediaItem {
  url?: string | null; file?: string | null; caption?: string | null; kind?: string;
  approved?: boolean; source?: string | null; licence?: string | null;
}

export interface Project extends ProjectRef {
  city: string;
  district: string | null;
  status: string;
  launch_date: string | null;
  handover_date: string | null;
  is_demo_data: boolean;
  /** Shown on the public marketing website and to the public assistant. */
  is_published: boolean;
  building_count: number;
  units: StatusCounts;
  price_from: string | null;
  price_to: string | null;
}

export interface Building { id: string; project_id: string; code: string; name: string; floors: number; is_demo_data: boolean; units: StatusCounts }

export interface PaymentPlan {
  id: string;
  project_id: string;
  name: string;
  down_payment_pct: string;
  installments: number;
  installment_frequency: string;
  handover_pct: string;
  description: string | null;
  is_active: boolean;
  is_demo_data: boolean;
  /** Phase 7C: only "cleared" plans appear in marketing (website, assistant, brochures, posters). */
  marketing_status: MarketingStatus;
}
export type MarketingStatus = "unreviewed" | "cleared" | "excluded";

export interface ProjectDetail extends Project {
  description: string | null;
  amenities: string[];
  media: MediaItem[];
  buildings: Building[];
  payment_plans: PaymentPlan[];
  address: string | null;
  country: string | null;
  latitude: string | null;
  longitude: string | null;
  location_verified: boolean;
  location_verified_at: string | null;
  location_verified_by: string | null;
  illustrative_label: string | null;
  illustrative_latitude: string | null;
  illustrative_longitude: string | null;
  illustrative_source: string | null;
  can_manage: boolean;
  created_at: string;
}

export interface Unit {
  id: string;
  project: ProjectRef;
  building: { id: string; code: string; name: string };
  unit_number: string;
  unit_type: string;
  bedrooms: number;
  bathrooms: number;
  floor: number;
  area_sqm: string;
  view: string | null;
  list_price: string;
  price_per_sqm: string;
  status: UnitStatus;
  is_public: boolean;
  is_demo_data: boolean;
}

export interface PlanBreakdown {
  plan_id: string;
  name: string;
  down_payment_pct: string;
  down_payment: string;
  installments: number;
  installment_frequency: string;
  installment_amount: string | null;
  last_installment_amount: string | null;
  handover_pct: string;
  handover_payment: string;
  total: string;
}

export interface UnitDetail extends Unit {
  notes: string | null;
  payment_plans: PlanBreakdown[];
  allowed_status_changes: string[];
  can_manage: boolean;
  created_at: string;
  updated_at: string;
}

export interface GridUnit { id: string; unit_number: string; unit_type: string; bedrooms: number; area_sqm: string; list_price: string; status: UnitStatus }
export interface Availability {
  project: ProjectRef;
  totals: StatusCounts;
  buildings: { id: string; code: string; name: string; floors: number; units: StatusCounts; rows: { floor: number; units: GridUnit[] }[] }[];
}

export interface UnitReservationInfo {
  code: string;
  status: string;
  reserved_at: string;
  expires_at: string;
  reserved_by: string | null;
  lead: { id: string; code: string; name: string } | null;
  reservation_id: string | null;
}

export type UnitFilters = ListQuery & {
  project_id?: string;
  building_id?: string;
  status?: string;
  unit_type?: string;
  bedrooms?: string;
  min_bedrooms?: string;
  price_min?: string;
  price_max?: string;
};

const key = ["realestate"] as const;

export function useProjects(query: ListQuery & { status?: string } = {}) {
  return useQuery({
    queryKey: [...key, "projects", query],
    queryFn: ({ signal }) => api.get<Page<Project>>("/realestate/projects", { page_size: 50, ...query }, signal),
    placeholderData: keepPreviousData,
  });
}

export function useProject(id: string | undefined) {
  return useQuery({ queryKey: [...key, "project", id], queryFn: () => api.get<ProjectDetail>(`/realestate/projects/${id}`), enabled: Boolean(id) });
}

export function useAvailability(id: string | undefined) {
  return useQuery({ queryKey: [...key, "availability", id], queryFn: () => api.get<Availability>(`/realestate/projects/${id}/availability`), enabled: Boolean(id) });
}

export function useUnits(query: UnitFilters, enabled = true) {
  return useQuery({
    queryKey: [...key, "units", query],
    queryFn: ({ signal }) => api.get<Page<Unit>>("/realestate/units", { ...query }, signal),
    placeholderData: keepPreviousData,
    enabled,
  });
}

export function useUnit(id: string | undefined) {
  return useQuery({ queryKey: [...key, "unit", id], queryFn: () => api.get<UnitDetail>(`/realestate/units/${id}`), enabled: Boolean(id) });
}

export function useUnitReservation(id: string | undefined) {
  return useQuery({
    queryKey: [...key, "unit", id, "reservation"],
    queryFn: () => api.get<UnitReservationInfo | null>(`/crm/units/${id}/reservation`),
    enabled: Boolean(id),
  });
}

export function useUpdateUnit(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Record<string, unknown>) => api.patch<UnitDetail>(`/realestate/units/${id}`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: key }),
  });
}

// --- management (realestate.inventory.manage; the API enforces it) -------------------------------------
export interface ProjectInput {
  code?: string;
  name: string;
  city: string;
  district: string | null;
  description: string | null;
  status: string;
  launch_date: string | null;
  handover_date: string | null;
  amenities: string[];
  media: MediaItem[];
  is_published?: boolean;
  address: string | null;
  country: string | null;
  latitude: string | null;
  longitude: string | null;
  location_verified: boolean;
  illustrative_label: string | null;
  illustrative_latitude: string | null;
  illustrative_longitude: string | null;
  illustrative_source: string | null;
}
export interface BuildingInput { code?: string; name: string; floors: number }
export interface PlanInput {
  name: string;
  down_payment_pct: string;
  installments: number;
  installment_frequency: string;
  handover_pct: string;
  description: string | null;
  is_active: boolean;
  marketing_status: MarketingStatus;
}

function useInvalidateInventory() {
  const qc = useQueryClient();
  return () => Promise.all([qc.invalidateQueries({ queryKey: key }), qc.invalidateQueries({ queryKey: ["crm"] })]);
}

export function useSaveProject(id?: string) {
  const invalidate = useInvalidateInventory();
  return useMutation({
    mutationFn: (body: ProjectInput) =>
      id ? api.patch<ProjectDetail>(`/realestate/projects/${id}`, body) : api.post<ProjectDetail>("/realestate/projects", body),
    onSuccess: invalidate,
  });
}

export function useSaveBuilding(projectId: string, id?: string) {
  const invalidate = useInvalidateInventory();
  return useMutation({
    mutationFn: (body: BuildingInput) =>
      id ? api.patch<Building>(`/realestate/buildings/${id}`, { name: body.name, floors: body.floors })
        : api.post<Building>(`/realestate/projects/${projectId}/buildings`, body),
    onSuccess: invalidate,
  });
}

export function useSavePlan(projectId: string, id?: string) {
  const invalidate = useInvalidateInventory();
  return useMutation({
    mutationFn: (body: PlanInput) =>
      id ? api.patch<PaymentPlan>(`/realestate/payment-plans/${id}`, body) : api.post<PaymentPlan>(`/realestate/projects/${projectId}/payment-plans`, body),
    onSuccess: invalidate,
  });
}

export function useSaveUnit(id?: string) {
  const invalidate = useInvalidateInventory();
  return useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      id ? api.patch<UnitDetail>(`/realestate/units/${id}`, body) : api.post<UnitDetail>("/realestate/units", body),
    onSuccess: invalidate,
  });
}
