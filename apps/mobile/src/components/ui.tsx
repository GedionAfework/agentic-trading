import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
  type TextInputProps,
  type ViewProps,
} from "react-native";
import { colors, space } from "../theme";

export function Screen({ children, style, ...rest }: ViewProps) {
  return (
    <View style={[styles.screen, style]} {...rest}>
      {children}
    </View>
  );
}

export function ScreenScroll({ children }: { children: React.ReactNode }) {
  return (
    <ScrollView
      style={styles.screen}
      contentContainerStyle={styles.scrollContent}
      keyboardShouldPersistTaps="handled"
    >
      {children}
    </ScrollView>
  );
}

export function Title({ children }: { children: React.ReactNode }) {
  return <Text style={styles.title}>{children}</Text>;
}

export function Muted({ children }: { children: React.ReactNode }) {
  return <Text style={styles.muted}>{children}</Text>;
}

export function Card({ children, style }: ViewProps) {
  return <View style={[styles.card, style]}>{children}</View>;
}

export function Field(props: TextInputProps) {
  return (
    <TextInput
      placeholderTextColor={colors.muted}
      autoCapitalize="none"
      autoCorrect={false}
      {...props}
      style={[styles.input, props.style]}
    />
  );
}

export function Button({
  label,
  onPress,
  variant = "primary",
  disabled,
}: {
  label: string;
  onPress: () => void;
  variant?: "primary" | "ghost" | "danger";
  disabled?: boolean;
}) {
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled}
      style={({ pressed }) => [
        styles.btn,
        variant === "primary" && styles.btnPrimary,
        variant === "ghost" && styles.btnGhost,
        variant === "danger" && styles.btnDanger,
        (pressed || disabled) && { opacity: 0.6 },
      ]}
    >
      <Text
        style={[
          styles.btnText,
          variant === "ghost" && { color: colors.text },
        ]}
      >
        {label}
      </Text>
    </Pressable>
  );
}

export function Badge({
  label,
  tone = "default",
}: {
  label: string;
  tone?: "default" | "paper" | "ok" | "warn" | "bad";
}) {
  const bg =
    tone === "paper"
      ? "#3A2F0E"
      : tone === "ok"
        ? "#143528"
        : tone === "warn"
          ? "#3A2C12"
          : tone === "bad"
            ? "#3A1520"
            : colors.accentSoft;
  const fg =
    tone === "paper"
      ? colors.paper
      : tone === "ok"
        ? colors.success
        : tone === "warn"
          ? colors.warn
          : tone === "bad"
            ? colors.danger
            : colors.accent;
  return (
    <View style={[styles.badge, { backgroundColor: bg }]}>
      <Text style={[styles.badgeText, { color: fg }]}>{label}</Text>
    </View>
  );
}

export function Loading() {
  return (
    <View style={styles.center}>
      <ActivityIndicator color={colors.accent} />
    </View>
  );
}

export function ErrorText({ children }: { children: React.ReactNode }) {
  return <Text style={styles.error}>{children}</Text>;
}

export function Row({ children }: { children: React.ReactNode }) {
  return <View style={styles.row}>{children}</View>;
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  scrollContent: { padding: space.md, paddingBottom: space.xl * 2, gap: space.md },
  title: { color: colors.text, fontSize: 24, fontWeight: "700", letterSpacing: -0.3 },
  muted: { color: colors.muted, fontSize: 14, lineHeight: 20 },
  card: {
    backgroundColor: colors.card,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: 14,
    padding: space.md,
    gap: space.sm,
  },
  input: {
    backgroundColor: colors.card,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: 12,
    paddingHorizontal: space.md,
    paddingVertical: 12,
    color: colors.text,
    fontSize: 16,
  },
  btn: {
    borderRadius: 12,
    paddingVertical: 14,
    paddingHorizontal: space.md,
    alignItems: "center",
  },
  btnPrimary: { backgroundColor: colors.accent },
  btnGhost: { backgroundColor: "transparent", borderWidth: 1, borderColor: colors.border },
  btnDanger: { backgroundColor: colors.danger },
  btnText: { color: "#fff", fontWeight: "700", fontSize: 16 },
  badge: {
    alignSelf: "flex-start",
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 4,
  },
  badgeText: { fontSize: 12, fontWeight: "700", letterSpacing: 0.4 },
  center: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: colors.bg },
  error: { color: colors.danger, fontSize: 14 },
  row: { flexDirection: "row", flexWrap: "wrap", gap: space.sm, alignItems: "center" },
});
