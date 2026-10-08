import { useQuery } from "@tanstack/react-query";
import { Text } from "react-native";
import { api } from "../../src/api/client";
import {
  Badge,
  Card,
  ErrorText,
  Loading,
  Muted,
  ScreenScroll,
  Title,
} from "../../src/components/ui";
import { PAPER_LABEL } from "../../src/config";
import { colors } from "../../src/theme";

export default function JournalScreen() {
  const q = useQuery({ queryKey: ["journal"], queryFn: api.journal });
  if (q.isLoading) return <Loading />;
  return (
    <ScreenScroll>
      <Title>Journal</Title>
      <Badge label={`${PAPER_LABEL} cohort`} tone="paper" />
      <Muted>Paper cohort is never silently merged with backtest/manual.</Muted>
      {q.error ? <ErrorText>{(q.error as Error).message}</ErrorText> : null}
      {(q.data || []).map((e) => (
        <Card key={e.id}>
          <Text style={{ color: colors.text, fontWeight: "700" }}>
            {e.instrument_symbol} {e.timeframe} {e.direction}
          </Text>
          <Muted>
            {e.outcome} · R {e.realized_r ?? "—"} · {e.cohort}
          </Muted>
          <Muted>{e.summary}</Muted>
        </Card>
      ))}
      {!q.isLoading && (q.data || []).length === 0 ? <Muted>No journal entries yet.</Muted> : null}
    </ScreenScroll>
  );
}
