import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, apiUpload } from "@/lib/api-client";

export type Representation = "design" | "as_built" | "illustrative";
export type ModelStatus = "draft" | "approved" | "archived";

export interface PropertyModel {
  id: string; project_id: string; unit_id: string | null; unit_code: string | null; title: string; caption: string | null;
  representation: Representation; source: string | null; licence: string | null; status: ModelStatus; format: "glb" | "gltf" | null;
  size_bytes: number | null; sha256: string | null; original_filename: string | null; mesh_count: number | null; file_version: number;
  uploaded_at: string | null; uploaded_by: { id: string; full_name: string } | null; approved_at: string | null;
  approved_by: { id: string; full_name: string } | null; created_at: string; updated_at: string; publicly_visible: boolean;
  allowed_actions: string[];
}
export interface ModelInput {
  title: string; unit_id: string | null; representation: Representation; caption: string | null; source: string | null; licence: string | null;
}
export interface UploadLimits { formats: string[]; max_bytes: number }

export const REPRESENTATION_LABEL: Record<Representation, string> = {
  design: "Design model (architect's design)",
  as_built: "As built (captured from the finished building)",
  illustrative: "Illustrative (indicative only)",
};

const key = ["realestate", "models"];

export const useModels = (projectId: string) =>
  useQuery({ queryKey: [...key, projectId], queryFn: () => api.get<PropertyModel[]>(`/realestate/projects/${projectId}/models`) });

export const useModelLimits = () =>
  useQuery({ queryKey: [...key, "limits"], queryFn: () => api.get<UploadLimits>("/realestate/models/limits"), staleTime: Infinity });

export function useModelMutations(projectId: string) {
  const qc = useQueryClient();
  const done = () => qc.invalidateQueries({ queryKey: [...key, projectId] });
  return {
    create: useMutation({ mutationFn: (b: ModelInput) => api.post<PropertyModel>(`/realestate/projects/${projectId}/models`, b), onSuccess: done }),
    update: useMutation({ mutationFn: ({ id, ...b }: Partial<ModelInput> & { id: string }) => api.patch<PropertyModel>(`/realestate/models/${id}`, b), onSuccess: done }),
    upload: useMutation({ mutationFn: ({ id, file }: { id: string; file: File }) => apiUpload<PropertyModel>(`/realestate/models/${id}/file`, file), onSuccess: done }),
    act: useMutation({ mutationFn: ({ id, action }: { id: string; action: "approve" | "archive" | "restore" }) => api.post<PropertyModel>(`/realestate/models/${id}/${action}`), onSuccess: done }),
    remove: useMutation({ mutationFn: (id: string) => api.delete<void>(`/realestate/models/${id}`), onSuccess: done }),
  };
}

/** Same checks as the API (which is authoritative): extension and size. */
export function fileProblem(file: File, limits?: UploadLimits): string | null {
  const ext = file.name.toLowerCase().match(/\.(glb|gltf)$/)?.[1];
  if (!ext) return "Choose a .glb or .gltf file.";
  if (limits && file.size > limits.max_bytes) return `The file is larger than ${Math.round(limits.max_bytes / 1024 / 1024)} MB.`;
  if (file.size < 64) return "The file is too small to be a 3D model.";
  return null;
}

export const formatBytes = (n: number | null) =>
  n == null ? "—" : n < 1024 * 1024 ? `${(n / 1024).toFixed(0)} KB` : `${(n / 1024 / 1024).toFixed(1)} MB`;
