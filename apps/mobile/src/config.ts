import Constants from "expo-constants";
import { Platform } from "react-native";

/**
 * Never put Telegram/Ollama/DB secrets in the app.
 * Only the public API base URL is configured here.
 */
function defaultBaseUrl(): string {
  const fromEnv = process.env.EXPO_PUBLIC_API_BASE_URL?.trim();
  if (fromEnv) return fromEnv.replace(/\/$/, "");
  const extra = Constants.expoConfig?.extra as { apiBaseUrl?: string } | undefined;
  if (extra?.apiBaseUrl) return extra.apiBaseUrl.replace(/\/$/, "");
  // Android emulator cannot reach the host via 127.0.0.1
  if (Platform.OS === "android") return "http://10.0.2.2:8000/v1";
  return "http://127.0.0.1:8000/v1";
}

export const API_BASE_URL = defaultBaseUrl();
export const APP_SCHEME = "privatetrading";
export const PAPER_LABEL = "PAPER";
