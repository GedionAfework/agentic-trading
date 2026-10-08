import { Redirect, Tabs } from "expo-router";
import { Text } from "react-native";
import { useAuth } from "../../src/auth/AuthContext";
import { Loading } from "../../src/components/ui";
import { colors } from "../../src/theme";

function TabIcon({ label }: { label: string }) {
  return <Text style={{ fontSize: 16 }}>{label}</Text>;
}

export default function AppLayout() {
  const { ready, user } = useAuth();
  if (!ready) return <Loading />;
  if (!user) return <Redirect href="/login" />;

  return (
    <Tabs
      screenOptions={{
        headerStyle: { backgroundColor: colors.bg },
        headerTintColor: colors.text,
        tabBarStyle: {
          backgroundColor: colors.card,
          borderTopColor: colors.border,
        },
        tabBarActiveTintColor: colors.accent,
        tabBarInactiveTintColor: colors.muted,
      }}
    >
      <Tabs.Screen
        name="index"
        options={{ title: "Dashboard", tabBarIcon: () => <TabIcon label="⌂" /> }}
      />
      <Tabs.Screen
        name="setups/index"
        options={{ title: "Setups", href: "/(app)/setups", tabBarIcon: () => <TabIcon label="◎" /> }}
      />
      <Tabs.Screen
        name="setups/[id]"
        options={{ href: null, title: "Setup" }}
      />
      <Tabs.Screen
        name="ask"
        options={{ title: "Ask AI", tabBarIcon: () => <TabIcon label="?" /> }}
      />
      <Tabs.Screen
        name="paper"
        options={{ title: "Paper", tabBarIcon: () => <TabIcon label="P" /> }}
      />
      <Tabs.Screen
        name="more"
        options={{ title: "More", tabBarIcon: () => <TabIcon label="…" /> }}
      />
      <Tabs.Screen name="journal" options={{ href: null, title: "Journal" }} />
      <Tabs.Screen name="knowledge" options={{ href: null, title: "Knowledge" }} />
      <Tabs.Screen name="vision" options={{ href: null, title: "Screenshot" }} />
      <Tabs.Screen name="strategies" options={{ href: null, title: "Strategies" }} />
      <Tabs.Screen name="backtests" options={{ href: null, title: "Backtests" }} />
      <Tabs.Screen name="analytics" options={{ href: null, title: "Analytics" }} />
      <Tabs.Screen name="notifications" options={{ href: null, title: "Notifications" }} />
      <Tabs.Screen name="sessions" options={{ href: null, title: "Sessions" }} />
      <Tabs.Screen name="health" options={{ href: null, title: "System health" }} />
    </Tabs>
  );
}
