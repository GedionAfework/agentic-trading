import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocalSearchParams } from "expo-router";
import { Text } from "react-native";
import { api, ApiError } from "../../../src/api/client";
import {
  Badge,
  Button,
  Card,
  ErrorText,
  Loading,
  Muted,
  ScreenScroll,
  Title,
} from "../../../src/components/ui";
import { PAPER_LABEL } from "../../../src/config";
import { colors } from "../../../src/theme";
import { useState } from "react";

export default function SetupDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const qc = useQueryClient();
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const q = useQuery({
    queryKey: ["candidates"],
    queryFn: api.candidates,
  });
  const accept = useMutation({
    mutationFn: (decisionId: string) => api.acceptPaper(decisionId),
    onSuccess: async (trade) => {
      setMsg(`Opened ${PAPER_LABEL} trade ${trade.id} (${trade.status})`);
      await qc.invalidateQueries({ queryKey: ["paper-trades"] });
      await qc.invalidateQueries({ queryKey: ["paper-account"] });
    },
    onError: (e) => setErr(e instanceof ApiError ? e.message : "Accept failed"),
  });

  if (q.isLoading) return <Loading />;
  const c = (q.data || []).find((x) => x.id === id);
  if (!c) {
    return (
      <ScreenScroll>
        <Title>Setup</Title>
        <ErrorText>Candidate not found.</ErrorText>
      </ScreenScroll>
    );
  }
  const payload = c.payload || {};
  return (
    <ScreenScroll>
      <Title>
        {c.instrument_symbol} {c.timeframe}
      </Title>
      <Badge label={PAPER_LABEL} tone="paper" />
      <Card>
        <Text style={{ color: colors.text, fontWeight: "700" }}>Action {c.action}</Text>
        <Muted>
          {c.strategy_code} v{c.strategy_version_no} · {c.signal_type}
        </Muted>
        <Muted>Setup: {String(payload.setup_state || "—")}</Muted>
        <Muted>Confidence: {String(payload.confidence_band || "—")}</Muted>
        <Muted>
          Entry {String(payload.entry_price ?? "n/a")} · Stop {String(payload.stop_price ?? "n/a")} ·
          Target {String(payload.target_price ?? "n/a")} · R:R {String(payload.rr_ratio ?? "n/a")}
        </Muted>
        <Muted>Candle {c.candle_open_time}</Muted>
        <Muted>Publish {c.publish_state} · seen {c.seen_count}×</Muted>
        <Muted>Decision support only — numbers from deterministic engines.</Muted>
      </Card>
      {c.decision_record_id ? (
        <Button
          label={accept.isPending ? "Opening PAPER…" : `Accept as ${PAPER_LABEL} trade`}
          onPress={() => {
            setErr(null);
            setMsg(null);
            accept.mutate(c.decision_record_id!);
          }}
          disabled={accept.isPending}
        />
      ) : (
        <Muted>No decision record attached — cannot open paper trade.</Muted>
      )}
      {msg ? <Muted>{msg}</Muted> : null}
      {err ? <ErrorText>{err}</ErrorText> : null}
    </ScreenScroll>
  );
}
