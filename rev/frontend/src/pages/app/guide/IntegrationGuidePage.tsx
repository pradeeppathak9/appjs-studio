import { Stack, Tabs, Text } from "@mantine/core";
import { useSearchParams } from "react-router";
import { PageTitle } from "../../../components/data";
import { API_BASE } from "../../../config";
import { useAppContext } from "../../../lib/appContext";
import { GATEWAY_LABEL, type Gateway } from "../../../lib/gateways";
import { PhonePeGuide } from "./PhonePeGuide";
import { RazorpayGuide } from "./RazorpayGuide";

/** API reference for the app's enabled gateways, one tab each (?gateway= selects one). */
export function IntegrationGuidePage() {
  const { app } = useAppContext();
  const [params, setParams] = useSearchParams();
  const enabled: Gateway[] = [
    ...(app.phonepe_enabled ? (["phonepe"] as const) : []),
    ...(app.razorpay_enabled ? (["razorpay"] as const) : []),
  ];
  // With no gateway enabled, still show both, so the guide can be read before setup.
  const tabs: Gateway[] = enabled.length ? enabled : ["phonepe", "razorpay"];
  const asked = params.get("gateway") as Gateway | null;
  const current = asked && tabs.includes(asked) ? asked : tabs[0];

  return (
    <Stack gap={0}>
      <PageTitle
        title="Integration guide"
        description="The server-side API for this app. Every URL already carries this app's ID."
      />
      {enabled.length === 0 && (
        <Text size="sm" c="dimmed" mb="md">
          No payment gateway is enabled for this app yet; an admin can enable PhonePe or Razorpay.
        </Text>
      )}
      <Tabs
        value={current}
        onChange={(v) => v && setParams({ gateway: v }, { replace: true })}
        keepMounted={false}
      >
        {tabs.length > 1 && (
          <Tabs.List mb="lg">
            {tabs.map((g) => (
              <Tabs.Tab key={g} value={g}>
                {GATEWAY_LABEL[g]}
              </Tabs.Tab>
            ))}
          </Tabs.List>
        )}
        <Tabs.Panel value="phonepe">
          <PhonePeGuide app={app} apiBase={API_BASE} />
        </Tabs.Panel>
        <Tabs.Panel value="razorpay">
          <RazorpayGuide app={app} apiBase={API_BASE} />
        </Tabs.Panel>
      </Tabs>
    </Stack>
  );
}
