/**
 * What THIS client's instance has switched on.
 *
 * The engine is shared by every client. What makes one client's system feel
 * like theirs is their profile — which product areas they bought (`modules`)
 * and which capabilities inside them are on (`features`). Both come from
 * `profiles/<client>.json`, applied with org_config.py, and are read here so
 * the navigation only ever offers what that organisation actually has.
 *
 * Hiding a menu item is a courtesy, never a security boundary: the API
 * enforces authorisation on every route that does real work.
 */
import { apiFetch } from "@/lib/session";

export type ModuleKey = "compliance" | "screening" | "knowledge";

export type ClientConfig = {
  modules: ModuleKey[];
  features: Record<string, boolean>;
};

/**
 * Fall back to every module and no features. This is the behaviour an
 * unconfigured instance had before this endpoint existed: nav shows
 * everything, individual capabilities stay off until switched on. Failing
 * open on modules keeps a network blip from emptying someone's navigation
 * mid-session; failing closed on features keeps a blip from advertising a
 * capability the client never bought.
 */
export const DEFAULT_CLIENT_CONFIG: ClientConfig = {
  modules: ["compliance", "screening", "knowledge"],
  features: {},
};

export async function getClientConfig(): Promise<ClientConfig> {
  const cfg = await apiFetch<ClientConfig>("/org/config");
  return {
    modules: Array.isArray(cfg.modules) && cfg.modules.length
      ? cfg.modules
      : DEFAULT_CLIENT_CONFIG.modules,
    features: cfg.features ?? {},
  };
}

/** True only when the flag is explicitly on. Unknown flag ⇒ off. */
export function hasFeature(cfg: ClientConfig, name: string): boolean {
  return cfg.features[name] === true;
}
