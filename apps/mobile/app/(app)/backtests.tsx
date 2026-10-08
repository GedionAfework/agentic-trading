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

export default function BacktestsScreen() {
  const q = useQuery({ queryKey: ["backtests"], queryFn: api.backtests });
  if (q.isLoading) return <Loading />;
  return (
    <ScreenScroll>
      <Title>Backtests</Title>
      <Muted>Pinned replay jobs. Cohorts stay separate from paper/manual.</Muted>
      {q.error ? <ErrorText>{(q.error as Error).message}</ErrorText> : null}
      {(q.data || []).map((j) => (
        <Card key={String(j.id)}>
          <Text style={{ color: colors.text, fontWeight: "700" }}>
            {String(j.strategy_code)} v{String(j.strategy_version_no)}
          </Text>
          <Muted>
            {String(j.status)} · engine {String(j.engine_version)}
          </Muted>
        </Card>
      ))}
      {!q.isLoading && (q.data || []).length === 0 ? <Muted>No backtest jobs yet.</Muted> : null}
    </ScreenScroll>
  );
}
