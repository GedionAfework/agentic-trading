import { useState } from "react";
import { Text } from "react-native";
import * as ImagePicker from "expo-image-picker";
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

export default function VisionScreen() {
  const [caption, setCaption] = useState("BTCUSDT 1h");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);

  async function pickAndUpload() {
    setError(null);
    setResult(null);
    const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!perm.granted) {
      setError("Photo library permission is required.");
      return;
    }
    const picked = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ["images"],
      quality: 0.9,
    });
    if (picked.canceled || !picked.assets[0]) return;
    const asset = picked.assets[0];
    setBusy(true);
    try {
      const out = await api.uploadScreenshot(
        asset.uri,
        asset.fileName || "chart.jpg",
        asset.mimeType || "image/jpeg",
        caption,
      );
      setResult(out);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <ScreenScroll>
      <Title>Screenshot analysis</Title>
      <Muted>Vision never authorizes a trade. Optional caption: SYMBOL TIMEFRAME.</Muted>
      <Field value={caption} onChangeText={setCaption} placeholder="BTCUSDT 1h" />
      <Button
        label={busy ? "Uploading…" : "Pick chart image"}
        onPress={pickAndUpload}
        disabled={busy}
      />
      {error ? <ErrorText>{error}</ErrorText> : null}
      {result ? (
        <Card>
          <Text style={{ color: colors.text, fontWeight: "700" }}>
            Status {String(result.status)}
          </Text>
          <Muted>authorizes_trade={String(result.authorizes_trade)}</Muted>
          <Muted>{JSON.stringify(result.verification ?? {}, null, 0)}</Muted>
        </Card>
      ) : null}
    </ScreenScroll>
  );
}
