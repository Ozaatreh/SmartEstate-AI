import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, apiDownload, apiUpload, saveBlob } from "@/lib/api-client";
import type { Language } from "./api";

export type Section = "overview" | "location" | "amenities" | "units" | "prices" | "payment_plans" | "contact";
export type PosterFormat = "instagram_post" | "instagram_story" | "linkedin" | "facebook";
export type PosterTemplate = "classic" | "split" | "minimal";
export type Cta = "book_viewing" | "register_interest" | "enquire_now" | "visit_sales";

export interface ProjectChoice { id: string; code: string; name: string; is_demo_data: boolean }
export interface Option { id: string; label: string }
export interface UnitTypeFact { bedrooms: number; available: number; area_min_sqm: string; area_max_sqm: string; price_from_sar: string }
export interface PlanFact { name: string; down_payment_pct: string; installments: number; installment_frequency: string; handover_pct: string }
/** origin "project": an approved project image (also on the website); "upload": uploaded here for brochures/posters only. */
export interface ImageFact { id: string; caption: string | null; source: string; licence: string; origin: "project" | "upload" }
export interface FactSheet {
  project_id: string; code: string; name: string; city: string; district: string | null; status: string; handover_date: string | null;
  description: string | null; is_demo_data: boolean; amenities: string[]; available_units: number; price_from_sar: string | null;
  unit_types: UnitTypeFact[]; payment_plans: PlanFact[]; excluded_plans: number; images: ImageFact[];
  contact: { phone: string | null; email: string | null; website: string | null }; as_of: string; missing: string[];
}
export interface CollateralOptions {
  facts: FactSheet; key_facts: Record<Language, Option[]>; sections: Option[];
  formats: { id: PosterFormat; label: string; width: number; height: number }[]; templates: Option[]; ctas: Record<Language, Option[]>;
}
export interface BrochureRequest { project_id: string; language: Language; sections: Section[]; image_id: string | null }
export interface PosterRequest {
  project_id: string; language: Language; format: PosterFormat; template: PosterTemplate; image_id: string | null;
  show_price: boolean; facts: string[]; cta: Cta;
}
export interface Preview { html: string; width: number; height: number | null }

export const useCollateralProjects = () =>
  useQuery({ queryKey: ["collateral", "projects"], queryFn: () => api.get<ProjectChoice[]>("/marketing/collateral/projects") });

export const useCollateralOptions = (projectId: string | undefined) =>
  useQuery({
    queryKey: ["collateral", "options", projectId],
    queryFn: () => api.get<CollateralOptions>(`/marketing/collateral/projects/${projectId}`),
    enabled: !!projectId,
  });

export const useBrochurePreview = (req: BrochureRequest | null) =>
  useQuery({
    queryKey: ["collateral", "brochure-preview", req],
    queryFn: () => api.post<Preview>("/marketing/collateral/brochure/preview", req),
    enabled: !!req,
    placeholderData: keepPreviousData,
  });

export const usePosterPreview = (req: PosterRequest | null) =>
  useQuery({
    queryKey: ["collateral", "poster-preview", req],
    queryFn: () => api.post<Preview>("/marketing/collateral/poster/preview", req),
    enabled: !!req,
    placeholderData: keepPreviousData,
  });

export function useDownload(kind: "brochure" | "poster") {
  return useMutation({
    mutationFn: async (body: BrochureRequest | PosterRequest) => {
      const file = await apiDownload(`/marketing/collateral/${kind}`, body);
      saveBlob(file.blob, file.filename);
      return file;
    },
  });
}

export interface ImageRights { source: string; licence: string; caption: string }

/** Uploads an image used only by this project's brochures and posters (never the website); returns its id. */
export function useUploadCollateralImage(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ file, rights }: { file: File; rights: ImageRights }) => {
      const q = new URLSearchParams({ source: rights.source.trim(), licence: rights.licence.trim() });
      if (rights.caption.trim()) q.set("caption", rights.caption.trim());
      return apiUpload<ImageFact>(`/marketing/collateral/projects/${projectId}/images?${q}`, file);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["collateral", "options", projectId] }),
  });
}
