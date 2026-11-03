import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pressable, Text, View } from "react-native";
import { Link } from "expo-router";
import { api } from "../../src/api/client";
import type { TradingProfileOption } from "../../src/api/types";
import {
  Badge,
  Button,
  Card,
  ErrorText,
  Loading,
  Muted,
  ScreenScroll,
  Title,
} from "../../src/components/ui";
import { PAPER_LABEL } from "../../src/config";
import { colors, space } from "../../src/theme";

function ProfileCard({
  profile,
  busy,
  onSelect,
}: {
  profile: TradingProfileOption;
  busy: boolean;
  onSelect: () => void;
}) {
  const wr = (profile.validation.win_rate * 100).toFixed(1);
  const meanR = profile.validation.mean_r.toFixed(3);
  return (
    <Pressable onPress={onSelect} disabled={busy || profile.selected}>
      <Card
        style={{
          borderWidth: 1,
          borderColor: profile.selected ? colors.accent : colors.border,
          opacity: busy ? 0.7 : 1,
        }}
      >
        <View style={{ flexDirection: "row", justifyContent: "space-between", gap: space.sm }}>
          <Text style={{ color: colors.text, fontWeight: "700", flex: 1 }}>{profile.label}</Text>
          {profile.selected ? <Badge label="Active" tone="paper" /> : null}
        </View>
        <Muted>{profile.summary}</Muted>
        <Muted>
          Research WR {wr}% · mean R {meanR} · n={profile.validation.trades}
        </Muted>
        <Muted>
          {profile.code} v{profile.version_no} · {profile.symbol}
        </Muted>
        {!profile.selected ? (
          <View style={{ marginTop: space.sm }}>
            <Button label="Use this model" onPress={onSelect} disabled={busy} />
          </View>
        ) : null}
      </Card>
    </Pressable>
  );
}

export default function PaperScreen() {
  const queryClient = useQueryClient();
  const account = useQuery({ queryKey: ["paper-account"], queryFn: api.paperAccount });
  const profile = useQuery({ queryKey: ["trading-profile"], queryFn: api.tradingProfile });
  const trades = useQuery({ queryKey: ["paper-trades"], queryFn: api.paperTrades });
  const setProfile = useMutation({
    mutationFn: (objective: "profit" | "win_rate") => api.setTradingProfile(objective),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["trading-profile"] }),
        queryClient.invalidateQueries({ queryKey: ["paper-account"] }),
      ]);
    },
  });

  if (account.isLoading || profile.isLoading) return <Loading />;

  const profiles = profile.data?.profiles || account.data?.trading_profile?.profiles || [];

  return (
    <ScreenScroll>
      <Title>Paper portfolio</Title>
      <Badge label={PAPER_LABEL} tone="paper" />
      <Muted>Forward validation without live money. Fills use next-open + costs.</Muted>
      {account.error ? <ErrorText>{(account.error as Error).message}</ErrorText> : null}
      {profile.error ? <ErrorText>{(profile.error as Error).message}</ErrorText> : null}

      <Title>Trading model</Title>
      <Muted>
        Pick which frozen SOL paper model the scanner uses. Live alerts stay blocked.
      </Muted>
      {setProfile.error ? <ErrorText>{(setProfile.error as Error).message}</ErrorText> : null}
      {profiles.map((p) => (
        <ProfileCard
          key={p.objective}
          profile={p}
          busy={setProfile.isPending}
          onSelect={() => setProfile.mutate(p.objective)}
        />
      ))}
      {profile.data?.note ? <Muted>{profile.data.note}</Muted> : null}

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
