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

export default function KnowledgeScreen() {
  const q = useQuery({ queryKey: ["documents"], queryFn: api.documents });
  if (q.isLoading) return <Loading />;
  return (
    <ScreenScroll>
      <Title>Knowledge library</Title>
      <Muted>Approved documents only feed Ask AI citations.</Muted>
      {q.error ? <ErrorText>{(q.error as Error).message}</ErrorText> : null}
      {(q.data || []).map((d) => (
        <Card key={String(d.id)}>
          <Text style={{ color: colors.text, fontWeight: "700" }}>{String(d.title)}</Text>
          <Muted>
            {String(d.document_type)} · tier {String(d.authority_tier)} · {String(d.status)}
          </Muted>
        </Card>
      ))}
      {!q.isLoading && (q.data || []).length === 0 ? <Muted>No documents uploaded.</Muted> : null}
    </ScreenScroll>
  );
}
