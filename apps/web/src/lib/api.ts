import type { User } from "firebase/auth";

export interface RaseedUser {
  id: string;
  firebase_uid: string;
  email: string | null;
  display_name: string | null;
  currency: string;
  timezone: string;
  locale: string;
  created_at: string;
  updated_at: string;
}

export class ApiError extends Error {
  constructor(public readonly status: number) {
    super(status === 401 ? "Your session could not be verified. Please sign in again."
      : "We couldn't load your account. Please try again.");
  }
}

export async function getMe(user: Pick<User, "getIdToken">, signal?: AbortSignal): Promise<RaseedUser> {
  const token = await user.getIdToken();
  const baseUrl = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");
  const response = await fetch(`${baseUrl}/api/v1/me`, {
    headers: { Authorization: `Bearer ${token}` },
    credentials: "omit",
    cache: "no-store",
    signal,
  });
  if (!response.ok) throw new ApiError(response.status);
  const body: { data: RaseedUser } = await response.json();
  return body.data;
}
