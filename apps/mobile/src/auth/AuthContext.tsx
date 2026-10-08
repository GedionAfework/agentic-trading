import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import * as Device from "expo-device";
import { api } from "../api/client";
import type { MeResponse } from "../api/types";
import { clearTokens, loadTokens, saveTokens } from "./storage";

type AuthState = {
  ready: boolean;
  user: MeResponse | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshMe: () => Promise<void>;
};

const Ctx = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [user, setUser] = useState<MeResponse | null>(null);

  const refreshMe = useCallback(async () => {
    const { access } = await loadTokens();
    if (!access) {
      setUser(null);
      return;
    }
    try {
      setUser(await api.me());
    } catch {
      setUser(null);
    }
  }, []);

  useEffect(() => {
    (async () => {
      try {
        await refreshMe();
      } finally {
        setReady(true);
      }
    })();
  }, [refreshMe]);

  const login = useCallback(async (email: string, password: string) => {
    const device =
      Device.modelName || Device.deviceName || Device.osName || "mobile";
    const tokens = await api.login(email.trim(), password, `mobile:${device}`);
    await saveTokens(tokens.access_token, tokens.refresh_token);
    setUser(await api.me());
  }, []);

  const logout = useCallback(async () => {
    const { refresh } = await loadTokens();
    try {
      await api.logout(refresh);
    } catch {
      /* still clear local */
    }
    await clearTokens();
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({ ready, user, login, logout, refreshMe }),
    [ready, user, login, logout, refreshMe],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useAuth outside AuthProvider");
  return ctx;
}
