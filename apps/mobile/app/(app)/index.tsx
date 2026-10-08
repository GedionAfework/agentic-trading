import { useQuery } from "@tanstack/react-query";
import { Text } from "react-native";
import { Link } from "expo-router";
import { api } from "../../src/api/client";
import { useAuth } from "../../src/auth/AuthContext";
import {
  Badge,
  Card,
  ErrorText,
  Loading,
  Muted,
  ScreenScroll,
  Title,
} from "../../src/components/ui";
import { API_BASE_URL, PAPER_LABEL } from "../../src/config";
import { colors } from "../../src/theme";

export default function DashboardScreen() {
  const { user } = useAuth();
  const scanner = useQuery({ queryKey: ["scanner-status"], queryFn: api.scannerStatus });
  const paper = useQuery({ queryKey: ["paper-account"], queryFn: api.paperAccount });
  const candidates = useQuery({ queryKey: ["candidates"], queryFn: api.candidates });

  if (scanner.isLoading && paper.isLoading) return <Loading />;

  return (
    <ScreenScroll>
      <Title>Dashboard</Title>
      <Muted>
        Signed in as {user?.email} · roles: {(user?.roles || []).join(", ")}
      </Muted>
      <Muted>API {API_BASE_URL}</Muted>

      <Card>
        <Text style={{ color: colors.text, fontWeight: "700" }}>Safety</Text>
        <Muted>Decision support only. Live broker execution is disabled.</Muted>
        <Badge label={PAPER_LABEL} tone="paper" />
      </Card>

      <Card>
        <Text style={{ color: colors.text, fontWeight: "700" }}>Scanner</Text>
        {scanner.error ? (
          <ErrorText>{(scanner.error as Error).message}</ErrorText>
        ) : (
          <>
            <Muted>
              candidates {scanner.data?.candidates_total ?? "—"} · published{" "}
              {scanner.data?.candidates_published ?? "—"} · dead letters{" "}
              {scanner.data?.dead_letters ?? "—"}
            </Muted>
            <Muted>
              scanner{" "}
              {scanner.data?.switches.scanner_enabled ? "ON" : "OFF"} · notifications{" "}
              {scanner.data?.switches.notifications_enabled ? "ON" : "OFF"}
            </Muted>
          </>
        )}
        <Link href="/(app)/setups" style={{ color: colors.accent, marginTop: 8 }}>
          View setups →
        </Link>
      </Card>

      <Card>
        <Text style={{ color: colors.text, fontWeight: "700" }}>Paper portfolio</Text>
        {paper.error ? (
          <ErrorText>{(paper.error as Error).message}</ErrorText>
        ) : (
          <>
            <Badge label={String(paper.data?.label || PAPER_LABEL)} tone="paper" />
            <Muted>
              equity {paper.data?.equity ?? "—"} {paper.data?.currency}
            </Muted>
            <Muted>
              closed {paper.data?.closed_trades ?? 0} · sum R {paper.data?.sum_realized_r ?? "—"}
            </Muted>
            <Muted>
              soak day {String(paper.data?.soak?.days_elapsed ?? "—")}/
              {String(paper.data?.soak?.days_required ?? "—")} · integrity{" "}
              {paper.data?.integrity?.ok ? "ok" : "defects"}
            </Muted>
          </>
        )}
        <Link href="/(app)/paper" style={{ color: colors.accent, marginTop: 8 }}>
          Open paper →
        </Link>
      </Card>

      <Card>
        <Text style={{ color: colors.text, fontWeight: "700" }}>Recent candidates</Text>
        <Muted>{(candidates.data || []).length} loaded</Muted>
        {(candidates.data || []).slice(0, 3).map((c) => (
          <Link key={c.id} href={`/(app)/setups/${c.id}`} style={{ color: colors.text }}>
            {c.instrument_symbol} {c.timeframe} · {c.action}
          </Link>
        ))}
      </Card>
    </ScreenScroll>
  );
}
