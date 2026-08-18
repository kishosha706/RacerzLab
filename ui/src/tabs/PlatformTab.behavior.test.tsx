import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { TraceResponse } from "../types/telemetry";
import { LocalPlatformTrace, type LocalTraceChannel } from "./PlatformTab";


function trace(values: Array<number | null>): TraceResponse {
  const xs = values.map((_value, index) => index * 10);
  return {
    run_id: "run-1",
    lap: 4,
    x_name: "lap_dist_ft",
    x_unit: "ft",
    x: xs,
    x_by_name: { lap_dist_ft: xs },
    channels: {
      custom_proxy: {
        unit: "proxy",
        values,
      },
    },
    sample_count: values.length,
    downsample: 1,
  };
}


const proxyChannel: LocalTraceChannel = {
  name: "custom_proxy",
  label: "Custom Proxy",
  color: "#f59e0b",
  isProxy: true,
  unit: "proxy",
};


describe("local Platform trace truth", () => {
  it("renders null as a real gap and keeps proxy styling structural", () => {
    const values = [1, 2, 3, 4, null, 6, 7, 8, 9];
    const xs = values.map((_value, index) => index * 10);
    const { container } = render(
      <LocalPlatformTrace
        trace={trace(values)}
        xs={xs}
        centerIndex={6}
        channels={[proxyChannel]}
        contextLabel="Lap 4 · exact physical window"
      />,
    );

    const visibleSegments = container.querySelectorAll(
      "polyline.platform-local-trace-line",
    );
    expect(visibleSegments).toHaveLength(2);
    for (const segment of visibleSegments) {
      expect(segment.getAttribute("stroke-dasharray")).toBe("7 6");
      expect(segment.parentElement?.getAttribute("data-channel-basis")).toBe(
        "proxy",
      );
    }
    expect(
      container.textContent?.toLowerCase(),
    ).toContain("proxies dashed");
    expect(
      container.querySelector(
        'svg[role="img"][aria-label="Local telemetry trace for Lap 4 · exact physical window"]',
      ),
    ).not.toBeNull();
  });

  it("does not bridge isolated finite samples across missing telemetry", () => {
    const values = [1, null, 3, null, 5];
    const xs = values.map((_value, index) => index * 10);
    const { container } = render(
      <LocalPlatformTrace
        trace={trace(values)}
        xs={xs}
        centerIndex={1}
        channels={[proxyChannel]}
        contextLabel="Sparse physical window"
      />,
    );

    expect(
      container.querySelectorAll("polyline.platform-local-trace-line"),
    ).toHaveLength(0);
    expect(container.textContent).toContain("Unavailable");
  });
});
