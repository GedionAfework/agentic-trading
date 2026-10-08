import * as SecureStore from "expo-secure-store";
import { Platform } from "react-native";

const ACCESS = "pta_access_token";
const REFRESH = "pta_refresh_token";

async function setItem(key: string, value: string): Promise<void> {
  if (Platform.OS === "web") {
    globalThis.localStorage?.setItem(key, value);
    return;
  }
  await SecureStore.setItemAsync(key, value);
}

async function getItem(key: string): Promise<string | null> {
  if (Platform.OS === "web") {
    return globalThis.localStorage?.getItem(key) ?? null;
  }
  return SecureStore.getItemAsync(key);
}

async function deleteItem(key: string): Promise<void> {
  if (Platform.OS === "web") {
    globalThis.localStorage?.removeItem(key);
    return;
  }
  await SecureStore.deleteItemAsync(key);
}

export async function saveTokens(access: string, refresh: string): Promise<void> {
  await setItem(ACCESS, access);
  await setItem(REFRESH, refresh);
}

export async function loadTokens(): Promise<{ access: string | null; refresh: string | null }> {
  const [access, refresh] = await Promise.all([getItem(ACCESS), getItem(REFRESH)]);
  return { access, refresh };
}

export async function clearTokens(): Promise<void> {
  await Promise.all([deleteItem(ACCESS), deleteItem(REFRESH)]);
}
