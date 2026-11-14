import { createRootRoute, createRoute, createRouter, Outlet } from "@tanstack/react-router";
import { Account } from "./pages/account";
import { Admin } from "./pages/admin";
import { Login, Signup, TokenLanding } from "./pages/auth";
import { Editor } from "./pages/editor";
import { FormsList } from "./pages/forms";
import { Billing, Payments, Settings, Team } from "./pages/org";
import { Responses, Results } from "./pages/responses";
import { Scan } from "./pages/scan";
import { Home, NewOrganization, OrgLayout, Protected } from "./pages/shell";

const root = createRootRoute({ component: Outlet });
const pub = <const P extends string>(path: P, component: () => React.ReactNode) => createRoute({ getParentRoute: () => root, path, component });

const login = pub("/login", Login);
const signup = pub("/signup", Signup);
const verify = pub("/auth/verify-email", () => <TokenLanding kind="verify-email" />);
const magic = pub("/auth/magic", () => <TokenLanding kind="magic" />);
const reset = pub("/auth/reset-password", () => <TokenLanding kind="reset-password" />);
const invitation = pub("/invitations/accept", () => <TokenLanding kind="invitation" />);

const app = createRoute({ getParentRoute: () => root, id: "app", component: Protected });
const inApp = <const P extends string>(path: P, component: () => React.ReactNode) => createRoute({ getParentRoute: () => app, path, component });
const home = inApp("/", Home);
const newOrg = inApp("/new-organization", NewOrganization);
const account = inApp("/account", Account);
const admin = inApp("/admin", Admin);

const org = createRoute({ getParentRoute: () => app, path: "/o/$org", component: OrgLayout });
const inOrg = <const P extends string>(path: P, component: () => React.ReactNode) => createRoute({ getParentRoute: () => org, path, component });
const orgRoutes = [
  inOrg("/", FormsList), inOrg("/forms/$form", Editor), inOrg("/forms/$form/responses", Responses), inOrg("/forms/$form/results", Results),
  inOrg("/payments", Payments), inOrg("/scan", Scan), inOrg("/team", Team), inOrg("/billing", Billing), inOrg("/settings", Settings),
];

const tree = root.addChildren([login, signup, verify, magic, reset, invitation, app.addChildren([home, newOrg, account, admin, org.addChildren(orgRoutes)])]);
export const router = createRouter({ routeTree: tree, defaultPreload: "intent" });

declare module "@tanstack/react-router" {
  interface Register { router: typeof router }
}
