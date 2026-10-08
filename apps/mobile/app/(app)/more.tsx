import { Pressable, Text } from "react-native";
import { router } from "expo-router";
import { useAuth } from "../../src/auth/AuthContext";
import { Button, Card, Muted, ScreenScroll, Title } from "../../src/components/ui";
import { colors } from "../../src/theme";

const LINKS: Array<{ href: string; title: string; blurb: string }> = [
  { href: "/(app)/journal", title: "Journal", blurb: "PAPER closed-trade journal" },
  { href: "/(app)/knowledge", title: "Knowledge library", blurb: "Approved documents" },
  { href: "/(app)/vision", title: "Screenshot analysis", blurb: "Vision never authorizes a trade" },
  { href: "/(app)/strategies", title: "Strategies", blurb: "Read-only strategy list" },
  { href: "/(app)/backtests", title: "Backtests", blurb: "Pinned replay jobs" },
  { href: "/(app)/analytics", title: "Analytics", blurb: "Phase 18 — placeholder" },
  { href: "/(app)/notifications", title: "Notifications", blurb: "Telegram delivery status" },
  { href: "/(app)/sessions", title: "Security sessions", blurb: "Revoke device sessions" },
  { href: "/(app)/health", title: "System health", blurb: "API / scanner / provider" },
];

export default function MoreScreen() {
  const { user, logout } = useAuth();
  return (
    <ScreenScroll>
      <Title>More</Title>
      <Muted>{user?.email}</Muted>
      {LINKS.map((item) => (
        <Pressable key={item.href} onPress={() => router.push(item.href as never)}>
          <Card>
            <Text style={{ color: colors.text, fontWeight: "700" }}>{item.title}</Text>
            <Muted>{item.blurb}</Muted>
          </Card>
        </Pressable>
      ))}
      <Button
        label="Sign out"
        variant="danger"
        onPress={async () => {
          await logout();
          router.replace("/login");
        }}
      />
    </ScreenScroll>
  );
}
