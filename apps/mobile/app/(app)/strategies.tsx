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

export default function StrategiesScreen() {
  const q = useQuery({ queryKey: ["strategies"], queryFn: api.strategies });
  if (q.isLoading) return <Loading />;
  return (
    <ScreenScroll>
      <Title>Strategies</Title>
      <Muted>Read-only in v1 mobile. Editing stays on the API / later editor.</Muted>
      {q.error ? <ErrorText>{(q.error as Error).message}</ErrorText> : null}
      {(q.data || []).map((s) => (
        <Card key={String(s.id || s.code)}>
          <Text style={{ color: colors.text, fontWeight: "700" }}>
            {String(s.code)} — {String(s.name || "")}
          </Text>
          <Muted>Status {String(s.status)}</Muted>
        </Card>
      ))}
    </ScreenScroll>
  );
}
