import { getApp, getApps, initializeApp } from "firebase/app";
import { browserSessionPersistence, getAuth, setPersistence, type Auth } from "firebase/auth";

const config = {
  apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY,
  authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN,
  projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID,
  appId: process.env.NEXT_PUBLIC_FIREBASE_APP_ID,
};

let authPromise: Promise<Auth> | undefined;

export function getFirebaseAuth(): Promise<Auth> {
  if (!Object.values(config).every(Boolean)) {
    return Promise.reject(new Error("Sign-in is not configured. Please try again later."));
  }
  if (!authPromise) {
    authPromise = (async () => {
      const app = getApps().length ? getApp() : initializeApp(config);
      const auth = getAuth(app);
      await setPersistence(auth, browserSessionPersistence);
      return auth;
    })().catch((error: unknown) => {
      authPromise = undefined;
      throw error;
    });
  }
  return authPromise;
}
