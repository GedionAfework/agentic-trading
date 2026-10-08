import { useQuery } from "@tanstack/react-query";
import { Text } from "react-native";
import { Link } from "expo-router";
import { api } from "../../../src/api/client";
import {
  Badge,
  Card,
  ErrorText,
  Loading,
  Muted,
  ScreenScroll,
  Title,
} from "../../../src/components/ui";
import { colors } from "../../../src/theme";

export default function SetupsScreen() {
  const q = useQuery({ queryKey: ["candidates"], queryFn: api.candidates });
  if (q.isLoading) return <Loading />;
  if (q.error) {
    return (
      <ScreenScroll>
        <Title>Setups</Title>
        <ErrorText>{(q.error as Error).message}</ErrorText>
      </ScreenScroll>
    );
  }
  const rows = q.data || [];
  return (
    <ScreenScroll>
      <Title>Setups</Title>
      <Muted>Scanner candidates from closed candles. Numbers come from stored engines.</Muted>
      {rows.length === 0 ? <Muted>No candidates yet.</Muted> : null}
      {rows.map((c) => {
        const payload = c.payload || {};
        return (
          <Link key={c.id} href={`/(app)/setups/${c.id}`} asChild>
            <Card>
              <Text style={{ color: colors.text, fontWeight: "700", fontSize: 16 }}>
                {c.instrument_symbol} · {c.timeframe}
              </Text>
              <Muted>
                {c.strategy_code} v{c.strategy_version_no} · {c.signal_type}
              </Muted>
              <Badge label={c.action} />
              <Muted>
                {String(payload.setup_state || "—")} · band{" "}
                {String(payload.confidence_band || "—")} · {c.publish_state}
              </Muted>
              <Muted>{c.candle_open_time}</Muted>
            </Card>
          </Link>
        );
      })}
    </ScreenScroll>
  );
}
