import { useQuery } from "@tanstack/react-query";
import { Text } from "react-native";
import { api } from "../../src/api/client";
import {
  Card,
  ErrorText,
  Loading,
  Muted,
  ScreenScroll,
  Title,
} from "../../src/components/ui";
import { colors } from "../../src/theme";

export default function NotificationsScreen() {
  const q = useQuery({ queryKey: ["telegram-status"], queryFn: api.telegramStatus });
  if (q.isLoading) return <Loading />;
  return (
    <ScreenScroll>
      <Title>Notifications</Title>
      <Muted>Telegram delivery status. Lock-screen payloads stay concise; deep links use privatetrading://</Muted>
      {q.error ? <ErrorText>{(q.error as Error).message}</ErrorText> : null}
      {q.data ? (
        <Card>
          <Text style={{ color: colors.text, fontWeight: "700" }}>Telegram</Text>
          <Muted>bot_configured={String(q.data.bot_configured)}</Muted>
          <Muted>webhook_secret_configured={String(q.data.webhook_secret_configured)}</Muted>
          <Muted>linked_accounts={String(q.data.linked_accounts)}</Muted>
          <Muted>updates_processed={String(q.data.updates_processed)}</Muted>
          <Muted>deliveries={JSON.stringify(q.data.deliveries || {})}</Muted>
        </Card>
      ) : null}
    </ScreenScroll>
  );
}
