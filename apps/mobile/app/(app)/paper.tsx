import { useQuery } from "@tanstack/react-query";
import { Text } from "react-native";
import { Link } from "expo-router";
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

export default function PaperScreen() {
  const account = useQuery({ queryKey: ["paper-account"], queryFn: api.paperAccount });
  const trades = useQuery({ queryKey: ["paper-trades"], queryFn: api.paperTrades });

  if (account.isLoading) return <Loading />;

  return (
    <ScreenScroll>
      <Title>Paper portfolio</Title>
      <Badge label={PAPER_LABEL} tone="paper" />
      <Muted>Forward validation without live money. Fills use next-open + costs.</Muted>
      {account.error ? <ErrorText>{(account.error as Error).message}</ErrorText> : null}
      {account.data ? (
        <Card>
          <Text style={{ color: colors.text, fontWeight: "700" }}>
            Equity {account.data.equity} {account.data.currency}
          </Text>
          <Muted>Starting {account.data.starting_equity}</Muted>
          <Muted>
            Closed {account.data.closed_trades} · sum R {account.data.sum_realized_r}
          </Muted>
          <Muted>
            Soak {String(account.data.soak.days_elapsed)}/
            {String(account.data.soak.days_required)} days · integrity{" "}
            {account.data.integrity.ok ? "ok" : "defects"}
          </Muted>
          <Muted>
            Fill policy {String(account.data.fill_model.fill_policy)} · ambiguity{" "}
            {String(account.data.fill_model.same_candle_ambiguity)}
          </Muted>
        </Card>
      ) : null}

      <Link href="/(app)/journal" style={{ color: colors.accent }}>
        Open PAPER journal →
      </Link>

      <Title>Trades</Title>
      {(trades.data || []).map((t) => (
        <Card key={t.id}>
          <Text style={{ color: colors.text, fontWeight: "700" }}>
            {t.instrument_symbol} {t.timeframe} {t.direction}
          </Text>
          <Badge label={t.label || PAPER_LABEL} tone="paper" />
          <Muted>
            {t.status}
            {t.exit_reason ? ` · ${t.exit_reason}` : ""}
          </Muted>
          <Muted>
            Entry {t.entry_price ?? t.planned_entry} · Stop {t.stop_price} · Target {t.target_price}
          </Muted>
          <Muted>
            R {t.realized_r ?? "—"} · pnl {t.realized_pnl ?? "—"}
          </Muted>
        </Card>
      ))}
      {!trades.isLoading && (trades.data || []).length === 0 ? (
        <Muted>No paper trades yet. Accept an ENTER setup from Setups.</Muted>
      ) : null}
    </ScreenScroll>
  );
}
