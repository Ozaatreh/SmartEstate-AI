import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type ListQuery, type Page } from "@/lib/api-client";

export interface EmployeeRef { id: string; employee_no: string; full_name: string; job_title: string }
export interface DepartmentRef { id: string; code: string; name: string }

export interface Department extends DepartmentRef {
  description: string | null;
  is_active: boolean;
  manager: EmployeeRef | null;
  headcount: number;
}

export interface Employee {
  id: string;
  employee_no: string;
  full_name: string;
  job_title: string;
  email: string | null;
  phone: string | null;
  location: string | null;
  hire_date: string | null;
  is_active: boolean;
  department: DepartmentRef;
  manager: EmployeeRef | null;
  user: { id: string; email: string; roles: string[] } | null;
  direct_reports_count: number;
}

export interface EmployeeDetail extends Employee {
  reporting_line: EmployeeRef[];
  direct_reports: EmployeeRef[];
  manages_departments: DepartmentRef[];
}

export interface EmployeeInput {
  full_name: string;
  job_title: string;
  department_id: string;
  manager_id: string | null;
  email: string | null;
  phone: string | null;
  location: string | null;
  hire_date: string | null;
}

const key = ["hr"] as const;

export function useDepartments(includeInactive = false) {
  return useQuery({
    queryKey: [...key, "departments", includeInactive],
    queryFn: () => api.get<Department[]>("/hr/departments", { include_inactive: includeInactive }),
    staleTime: 60_000,
  });
}

export function useEmployees(query: ListQuery & { department_id?: string; status?: string; manager_id?: string }, enabled = true) {
  return useQuery({
    queryKey: [...key, "employees", query],
    queryFn: ({ signal }) => api.get<Page<Employee>>("/hr/employees", { ...query }, signal),
    placeholderData: keepPreviousData,
    enabled,
  });
}

/** Lightweight list for pickers (active employees, up to 100). */
export function useEmployeeOptions(enabled = true) {
  return useEmployees({ page_size: 100, sort: "full_name" }, enabled);
}

export function useEmployee(id: string | undefined) {
  return useQuery({
    queryKey: [...key, "employee", id],
    queryFn: () => api.get<EmployeeDetail>(`/hr/employees/${id}`),
    enabled: Boolean(id),
  });
}

export function useSaveEmployee(id?: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Partial<EmployeeInput> & { is_active?: boolean }) =>
      id ? api.patch<EmployeeDetail>(`/hr/employees/${id}`, body) : api.post<EmployeeDetail>("/hr/employees", body),
    onSuccess: () => qc.invalidateQueries({ queryKey: key }),
  });
}

export function useSaveDepartment(id?: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { code?: string; name: string; description: string | null; manager_employee_id: string | null; is_active?: boolean }) =>
      id ? api.patch<Department>(`/hr/departments/${id}`, body) : api.post<Department>("/hr/departments", body),
    onSuccess: () => qc.invalidateQueries({ queryKey: key }),
  });
}
