import { Badge, Card, Muted, ScreenScroll, Title } from "../../src/components/ui";

export default function AnalyticsScreen() {
  return (
    <ScreenScroll>
      <Title>Analytics</Title>
      <Badge label="Phase 18" tone="warn" />
      <Card>
        <Muted>
          Performance snapshots, sample-size warnings, and calibration land in Phase 18. Mobile
          will consume those SQL aggregates — never LLM-invented stats.
        </Muted>
      </Card>
    </ScreenScroll>
  );
}
