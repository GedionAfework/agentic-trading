import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pressable, Text, View } from "react-native";
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
import { colors } from "../../src/theme";

export default function AnalyticsScreen() {
  const qc = useQueryClient();
  const perf = useQuery({
    queryKey: ["analytics", "performance"],
    queryFn: () => api.performance("paper", "overall"),
  });
  const cal = useQuery({
    queryKey: ["analytics", "calibration"],
    queryFn: () => api.calibration(),
  });
  const refresh = useMutation({
    mutationFn: async () => {
      await api.refreshPerformance("paper");
      await api.refreshCalibration();
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["analytics"] });
    },
  });
  const snap = (perf.data || [])[0];
  const narrate = useMutation({
    mutationFn: () => {
      if (!snap) throw new Error("No snapshot yet — refresh first");
      return api.narratePerformance(snap.id);
    },
  });

  if (perf.isLoading) return <Loading />;

  return (
    <ScreenScroll>
      <Title>Analytics</Title>
      <Badge label="PAPER cohort" tone="paper" />
      <Muted>SQL aggregates only. Backtest and paper cohorts are never merged.</Muted>

      <Pressable
        onPress={() => refresh.mutate()}
        style={{
          backgroundColor: colors.accent,
          padding: 12,
          borderRadius: 8,
          marginTop: 12,
          marginBottom: 8,
        }}
      >
        <Text style={{ color: "#fff", fontWeight: "700", textAlign: "center" }}>
          {refresh.isPending ? "Refreshing…" : "Refresh snapshots"}
        </Text>
      </Pressable>

      {perf.error ? <ErrorText>{(perf.error as Error).message}</ErrorText> : null}
      {refresh.error ? <ErrorText>{(refresh.error as Error).message}</ErrorText> : null}

      {snap ? (
        <Card>
          <Text style={{ color: colors.text, fontWeight: "700" }}>
            Overall · n={snap.sample_size}
          </Text>
          <Badge
            label={snap.sample_status}
            tone={snap.sample_status === "ok" ? "ok" : "warn"}
          />
          <Muted>
            Win rate {snap.metrics.win_rate ?? "—"} · mean R {snap.metrics.mean_r ?? "—"} · sum R{" "}
            {snap.metrics.sum_r ?? "—"}
          </Muted>
          {(snap.warnings || []).map((w) => (
            <Muted key={w}>{w}</Muted>
          ))}
          <Pressable onPress={() => narrate.mutate()} style={{ marginTop: 8 }}>
            <Text style={{ color: colors.accent, fontWeight: "600" }}>
              {narrate.isPending ? "Narrating…" : "Grounded narrative"}
            </Text>
          </Pressable>
          {narrate.data ? <Muted>{narrate.data.narrative}</Muted> : null}
          {narrate.error ? <ErrorText>{(narrate.error as Error).message}</ErrorText> : null}
        </Card>
      ) : (
        <Card>
          <Muted>No PAPER performance snapshot yet. Tap refresh after closed paper trades exist.</Muted>
        </Card>
      )}

      <View style={{ marginTop: 8 }}>
        <Text style={{ color: colors.text, fontWeight: "700", marginBottom: 4 }}>Calibration</Text>
        {(cal.data || []).map((c) => (
          <Card key={c.id}>
            <Muted>
              {c.band_field} · n={c.sample_size} · {c.sample_status}
            </Muted>
            {(c.drift_flags || []).length ? (
              <Muted>Drift: {c.drift_flags.join("; ")}</Muted>
            ) : (
              <Muted>Drift flags: none</Muted>
            )}
          </Card>
        ))}
        {!cal.isLoading && (cal.data || []).length === 0 ? (
          <Muted>No calibration snapshot yet.</Muted>
        ) : null}
      </View>
    </ScreenScroll>
  );
}
