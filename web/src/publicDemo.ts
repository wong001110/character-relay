import type { AuthUser } from "./api";

export const PUBLIC_DEMO_EMAIL = "demo@echo-masque.app";

export function isPublicDemoUser(user: AuthUser | null): boolean {
  return user?.email.toLocaleLowerCase() === PUBLIC_DEMO_EMAIL;
}
