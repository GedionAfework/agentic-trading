import { useState } from "react";
import { Text } from "react-native";
import { api, ApiError } from "../../src/api/client";
import {
  Button,
  Card,
  ErrorText,
  Field,
  Muted,
  ScreenScroll,
  Title,
} from "../../src/components/ui";
import { colors } from "../../src/theme";
import type { AskResponse } from "../../src/api/types";

export default function AskScreen() {
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AskResponse | null>(null);

  async function onAsk() {
    setBusy(true);
    setError(null);
    try {
      setResult(await api.ask(question.trim()));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Ask failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <ScreenScroll>
      <Title>Ask AI</Title>
      <Muted>Answers cite approved knowledge only. No invented numbers.</Muted>
      <Field
        value={question}
        onChangeText={setQuestion}
        placeholder="Ask a strategy question…"
        multiline
        style={{ minHeight: 100, textAlignVertical: "top" }}
      />
      <Button label={busy ? "Asking…" : "Ask"} onPress={onAsk} disabled={busy || !question.trim()} />
      {error ? <ErrorText>{error}</ErrorText> : null}
      {result ? (
        <Card>
          <Text style={{ color: colors.text, lineHeight: 22 }}>{result.answer}</Text>
          <Muted>
            Confidence {result.confidence}
            {result.sufficient_evidence ? "" : " · insufficient evidence"}
          </Muted>
          {(result.citations || []).map((c) => (
            <Muted key={c.chunk_id}>
              · {c.title}
              {c.page != null ? ` p.${c.page}` : ""} (tier {c.authority_tier})
            </Muted>
          ))}
          {(result.conflicts || []).length > 0 ? (
            <Muted>Conflicts: {result.conflicts.join("; ")}</Muted>
          ) : null}
        </Card>
      ) : null}
    </ScreenScroll>
  );
}
