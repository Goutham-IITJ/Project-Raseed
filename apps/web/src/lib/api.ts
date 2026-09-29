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
      : status === 404 ? "This item is no longer available or doesn't belong to your account."
      : status === 409 ? "This request conflicts with the latest record. Refresh before trying again."
      : status === 413 ? "This receipt is too large. Choose a file smaller than 10 MB."
      : status === 415 ? "This file could not be read. Use a JPG, PNG or unencrypted PDF."
      : status === 422 ? "Some details aren't valid. Check your entries and try again."
      : status === 0 ? "We couldn't reach Raseed. Check your connection and try again."
      : "Raseed couldn't complete this request. Please try again shortly.");
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
