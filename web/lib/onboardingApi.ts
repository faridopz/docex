/**
 * In-app onboarding wizard — client for api/onboarding_routes.py.
 *
 * An admin configures departments and the approval chain from inside DOCex
 * instead of a developer hand-editing profiles/<client>.json. Mirrors the
 * backend's SetupRequest/SetupResult shapes exactly.
 */
import { apiFetch } from "@/lib/session";

export type OnboardingStatus = {
  configured: boolean;
  departments_configured: boolean;
  workflow_configured: boolean;
  department_count: number;
  step_count: number;
};

export type DepartmentInput = {
  name: string;
  key?: string;
  is_final_authority?: boolean;
};

export type StepInput = {
  label: string;
  department: string;
  min_amount?: number;
  can_override?: boolean;
  override_limit?: number | null;
};

export type SetupRequest = {
  currency: string;
  departments: DepartmentInput[];
  workflow_size: "small" | "medium" | "large" | "custom";
  custom_steps?: StepInput[];
  max_amount?: number | null;
  allowed_categories?: string[];
  required_documents?: string[];
};

export type SetupResult = {
  ok: boolean;
  partial: boolean;
  departments: number;
  steps: number;
  error: string | null;
};

export async function getOnboardingStatus(): Promise<OnboardingStatus> {
  return apiFetch("/onboarding/status");
}

export async function runOnboardingSetup(body: SetupRequest): Promise<SetupResult> {
  return apiFetch("/onboarding/setup", { method: "POST", body: JSON.stringify(body) });
}
