import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError, setCsrf } from "./lib/api";

export interface Membership { organization_id: string; name: string; slug: string; role: string; plan_code: string }
export interface Me {
  id: string; email: string; display_name: string | null; locale: "fr" | "en"; email_verified: boolean;
  totp_enabled: boolean; mfa_passed: boolean; is_platform_admin: boolean; csrf_token: string; memberships: Membership[];
}
export interface Org {
  id: string; name: string; slug: string; plan_code: string; currency: string; role: string; verified: boolean;
  suspended: boolean; features: string[]; limits: Record<string, number | null>; viewer_can_export: boolean;
  is_nonprofit: boolean; referral_code: string;
}

export function useMe() {
  return useQuery<Me | null>({
    queryKey: ["me"],
    queryFn: async () => {
      try {
        const me = await api<Me>("/me");
        setCsrf(me.csrf_token);
        return me;
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) return null;
        throw e;
      }
    },
    staleTime: 60_000,
  });
}

export function useAcceptMe() {
  const qc = useQueryClient();
  return (me: Me) => {
    setCsrf(me.csrf_token);
    qc.setQueryData(["me"], me);
  };
}

export const useOrg = (orgId: string) => useQuery<Org>({ queryKey: ["org", orgId], queryFn: () => api(`/orgs/${orgId}`) });

const RANK: Record<string, number> = { viewer: 0, editor: 1, admin: 2, owner: 3 };
export const atLeast = (org: Org | undefined, role: string): boolean => (RANK[org?.role ?? "viewer"] ?? 0) >= (RANK[role] ?? 0);
