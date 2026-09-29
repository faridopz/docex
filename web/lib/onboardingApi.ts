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

// ─── the setup wizard (api/onboarding_routes.py → setup_wizard.py) ─────────

export type Signoff = {
  department: string;
  from_amount: number | null;
  can_release: boolean;
  release_limit: number | null;
};

export type WizardAnswers = {
  org_name: string;
  currency: string;
  address_lines: string[];
  rc_number: string;
  departments: { key?: string; name: string }[];
  first_approver: "budget_holder" | "department" | "none";
  first_department: string;
  policy_department: string;
  policy_can_release: boolean;
  policy_release_limit: number | null;
  signoffs: Signoff[];
  documents: string[];
  quotes_count: number;
  quotes_from: number | null;
  tender_from: number | null;
  quote_categories: string[];
  max_amount: number | null;
};

export type RouteBand = {
  from: number;
  to: number | null;
  span: string;
  steps: { label: string; who: string; may_release: boolean; release_limit: number | null }[];
};

export type WizardPreview = {
  ok: boolean;
  errors: string[];
  warnings: string[];
  route: RouteBand[];
  documents: string[];
  new_org: boolean;
  saved?: boolean;
};

export async function getWizardAnswers(): Promise<{ answers: WizardAnswers; categories: string[]; configured: boolean }> {
  return apiFetch("/onboarding/answers");
}

export async function previewWizard(answers: WizardAnswers): Promise<WizardPreview> {
  return apiFetch("/onboarding/preview", { method: "POST", body: JSON.stringify({ answers }) });
}

export async function applyWizard(answers: WizardAnswers): Promise<WizardPreview> {
  return apiFetch("/onboarding/apply", { method: "POST", body: JSON.stringify({ answers }) });
}
