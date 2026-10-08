import { useState } from "react";
import { KeyboardAvoidingView, Platform, StyleSheet, View } from "react-native";
import { Redirect, router } from "expo-router";
import { ApiError } from "../src/api/client";
import { useAuth } from "../src/auth/AuthContext";
import { Button, ErrorText, Field, Muted, Title } from "../src/components/ui";
import { API_BASE_URL } from "../src/config";
import { colors, space } from "../src/theme";

export default function LoginScreen() {
  const { user, login } = useAuth();
  const [email, setEmail] = useState("owner@example.com");
  const [password, setPassword] = useState("changeme-owner");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (user) return <Redirect href="/(app)" />;

  async function onSubmit() {
    setBusy(true);
    setError(null);
    try {
      await login(email, password);
      router.replace("/(app)");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Login failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <KeyboardAvoidingView
      style={styles.root}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <View style={styles.inner}>
        <Title>Private Trading</Title>
        <Muted>Decision support only — no live broker execution.</Muted>
        <Muted>API: {API_BASE_URL}</Muted>
        <Field
          value={email}
          onChangeText={setEmail}
          placeholder="Email"
          keyboardType="email-address"
          textContentType="username"
          autoComplete="email"
        />
        <Field
          value={password}
          onChangeText={setPassword}
          placeholder="Password"
          secureTextEntry
          textContentType="password"
          autoComplete="password"
        />
        {error ? <ErrorText>{error}</ErrorText> : null}
        <Button label={busy ? "Signing in…" : "Sign in"} onPress={onSubmit} disabled={busy} />
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bg, justifyContent: "center" },
  inner: { padding: space.lg, gap: space.md },
});
