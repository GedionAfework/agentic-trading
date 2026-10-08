import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Text } from "react-native";
import { api, ApiError } from "../../src/api/client";
import {
  Button,
  Card,
  ErrorText,
  Loading,
  Muted,
  ScreenScroll,
  Title,
} from "../../src/components/ui";
import { colors } from "../../src/theme";
import { useState } from "react";

export default function SessionsScreen() {
  const qc = useQueryClient();
  const [err, setErr] = useState<string | null>(null);
  const q = useQuery({ queryKey: ["sessions"], queryFn: api.sessions });
  const revoke = useMutation({
    mutationFn: (id: string) => api.revokeSession(id),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ["sessions"] });
    },
    onError: (e) => setErr(e instanceof ApiError ? e.message : "Revoke failed"),
  });

  if (q.isLoading) return <Loading />;
  return (
    <ScreenScroll>
      <Title>Security sessions</Title>
      <Muted>Revoke a device session to force re-login on that client.</Muted>
      {q.error ? <ErrorText>{(q.error as Error).message}</ErrorText> : null}
      {err ? <ErrorText>{err}</ErrorText> : null}
      {(q.data || []).map((s) => (
        <Card key={s.id}>
          <Text style={{ color: colors.text, fontWeight: "700" }}>
            {s.device_name || "unnamed device"}
          </Text>
          <Muted>Created {s.created_at}</Muted>
          <Muted>Expires {s.expires_at}</Muted>
          <Muted>{s.revoked_at ? `Revoked ${s.revoked_at}` : "Active"}</Muted>
          {!s.revoked_at ? (
            <Button
              label="Revoke"
              variant="danger"
              onPress={() => {
                setErr(null);
                revoke.mutate(s.id);
              }}
            />
          ) : null}
        </Card>
      ))}
    </ScreenScroll>
  );
}
