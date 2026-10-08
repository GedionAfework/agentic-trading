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
import { API_BASE_URL } from "../../src/config";
import { colors } from "../../src/theme";

export default function HealthScreen() {
  const health = useQuery({ queryKey: ["health"], queryFn: api.health });
  const scanner = useQuery({ queryKey: ["scanner-status"], queryFn: api.scannerStatus });
  if (health.isLoading) return <Loading />;
  return (
    <ScreenScroll>
      <Title>System health</Title>
      <Muted>{API_BASE_URL}</Muted>
      {health.error ? <ErrorText>{(health.error as Error).message}</ErrorText> : null}
      {health.data ? (
        <Card>
          <Text style={{ color: colors.text, fontWeight: "700" }}>
            API {health.data.status}
          </Text>
          <Muted>
            {health.data.service} · {health.data.env} · v{health.data.version}
          </Muted>
          <Muted>{JSON.stringify(health.data.checks || {})}</Muted>
        </Card>
      ) : null}
      {scanner.data ? (
        <Card>
          <Text style={{ color: colors.text, fontWeight: "700" }}>Scanner</Text>
          <Muted>version {scanner.data.scanner_version}</Muted>
          <Muted>
            switches {JSON.stringify(scanner.data.switches)} · dead_letters{" "}
            {scanner.data.dead_letters}
          </Muted>
          <Muted>provider {JSON.stringify(scanner.data.provider || {})}</Muted>
        </Card>
      ) : null}
    </ScreenScroll>
  );
}
