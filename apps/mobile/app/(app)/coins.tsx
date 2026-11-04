import { useQuery } from "@tanstack/react-query";
import { RefreshControl, Text, View } from "react-native";
import { api } from "../../src/api/client";
import type { DeskCoin } from "../../src/api/types";
import { Badge, Card, ErrorText, Loading, Muted, ScreenScroll, Title } from "../../src/components/ui";
import { PAPER_LABEL } from "../../src/config";
import { colors, space } from "../../src/theme";

function tone(headline: string): "ok" | "warn" | "paper" | "default" {
  if (headline === "ENTER" || headline === "IN PAPER TRADE") return "ok";
  if (headline === "ENTER (not opened)") return "warn";
  if (headline === "WATCH") return "paper";
  return "default";
}

const ROLE_LABEL: Record<DeskCoin["role"], string> = {
  paper: "Paper model",
  inactive_for_profile: "No model for this profile",
  watch: "Watch only",
};

function CoinCard({ coin }: { coin: DeskCoin }) {
  return (
    <Card>
      <View style={{ flexDirection: "row", justifyContent: "space-between", gap: space.sm }}>
        <Text style={{ color: colors.text, fontWeight: "700", fontSize: 16 }}>{coin.symbol}</Text>
        <Badge label={coin.headline} tone={tone(coin.headline)} />
      </View>
      <Muted>
        {ROLE_LABEL[coin.role]}
        {coin.model_code ? ` · ${coin.model_code}` : ""}
      </Muted>
      {coin.reasons.map((reason, i) => (
        <Text key={i} style={{ color: colors.text, marginTop: 2 }}>
          • {reason}
        </Text>
      ))}
      {coin.levels ? (
        <Muted>
          Entry {coin.levels.entry} · stop {coin.levels.stop} · target {coin.levels.target} · R:R{" "}
          {coin.levels.rr}
        </Muted>
      ) : null}
      {coin.research ? (
        <Muted>
          Research {coin.research.trades} trades · {(coin.research.win_rate * 100).toFixed(1)}% wins ·{" "}
          {coin.research.mean_r >= 0 ? "+" : ""}
          {coin.research.mean_r.toFixed(3)}R
        </Muted>
      ) : null}
      {coin.context ? <Muted>{coin.context}</Muted> : null}
      {coin.challenger ? (
        <Muted>
          Challenger (paper only, since {coin.challenger.forward_start.slice(0, 10)}):{" "}
          {coin.challenger.challenger?.closed_trades ?? 0} trades
          {coin.challenger.challenger?.mean_r != null
            ? ` · ${((coin.challenger.challenger.win_rate ?? 0) * 100).toFixed(1)}% wins · ${coin.challenger.challenger.mean_r.toFixed(3)}R`
            : ""}{" "}
          vs incumbent {coin.challenger.incumbent?.closed_trades ?? 0} trades
          {coin.challenger.incumbent?.mean_r != null
            ? ` · ${coin.challenger.incumbent.mean_r.toFixed(3)}R`
            : ""}
        </Muted>
      ) : null}
      {coin.last_scan?.candle_open_time ? (
        <Muted>Last scan: {coin.last_scan.candle_open_time.replace("T", " ").slice(0, 16)} UTC</Muted>
      ) : null}
    </Card>
  );
}

export default function CoinsScreen() {
  const desk = useQuery({
    queryKey: ["coin-desk"],
    queryFn: api.coinDesk,
    refetchInterval: 60_000,
  });

  if (desk.isLoading) return <Loading />;
  const data = desk.data;

  return (
    <ScreenScroll
      refreshControl={
        <RefreshControl refreshing={desk.isFetching} onRefresh={() => desk.refetch()} />
      }
    >
      <Title>My coins</Title>
      <Badge label={PAPER_LABEL} tone="paper" />
      <Muted>Why each coin is WAIT, WATCH or ENTER. Not a trade instruction.</Muted>
      {desk.error ? <ErrorText>{(desk.error as Error).message}</ErrorText> : null}
      {data ? (
        <>
          {!data.supervisor.paper_auto_open_enabled ? (
            <Card style={{ borderWidth: 1, borderColor: colors.border }}>
              <Text style={{ color: colors.text, fontWeight: "700" }}>Paper auto-open paused</Text>
              <Muted>{data.supervisor.pause_reasons.join(", ") || "Paused by owner."}</Muted>
              <Muted>Resume after inspecting: Telegram /settings paper on.</Muted>
            </Card>
          ) : null}
          <Card>
            <Muted>
              Profile {data.profile.objective} · {data.profile.model_code}
            </Muted>
            <Muted>
              Soak {data.soak.closed_trades ?? 0}/{data.soak.min_closed_trades ?? "?"} closed · mean{" "}
              {(data.soak.mean_r ?? 0).toFixed(3)}R
            </Muted>
            <Muted>
              Crypto risk {data.portfolio.crypto_open_risk_pct}% open · {data.portfolio.crypto_headroom_pct}% free
              {data.portfolio.daily_loss_stop_hit ? " · daily loss stop hit" : ""}
            </Muted>
            <Muted>
              BTC regime (shadow, not a filter): {data.btc_regime?.label ?? "unknown"}
            </Muted>
            {data.btc_regime_shadow?.models.map((m) => (
              <Muted key={m.model_code}>
                {m.model_code}: risk-on {m.risk_on.trades} / risk-off {m.risk_off.trades} closed ·{" "}
                {m.verdict}
              </Muted>
            ))}
          </Card>
          {data.coins.map((coin) => (
            <CoinCard key={coin.symbol} coin={coin} />
          ))}
        </>
      ) : null}
    </ScreenScroll>
  );
}
