/** Bridge so api client can push refreshed session users into AuthProvider. */

import type { UserPublic } from "@/services/auth/authApi";

type SessionUserHandler = (user: UserPublic | null) => void;

let handler: SessionUserHandler | null = null;

export function setSessionUserHandler(next: SessionUserHandler | null): void {
  handler = next;
}

export function notifySessionUser(user: UserPublic | null): void {
  handler?.(user);
}
