/** Destinations in the driver workflow, not claims of completed engineering work. */
export const WORKSPACE_JOURNEY: Record<string, { number: string; purpose: string; accent: string }> = {
  overview: { number: "01", purpose: "Get your bearings", accent: "#63d9ff" },
  engineer: { number: "02", purpose: "Follow the evidence", accent: "#ac9aff" },
  laps: { number: "03", purpose: "Find your rhythm", accent: "#65dfbd" },
  platform_trace: { number: "04", purpose: "Explore the signals", accent: "#63d9ff" },
  setup_impact: { number: "05", purpose: "Know your car", accent: "#f7bd73" },
  dial_in: { number: "06", purpose: "Plan one clean test", accent: "#ed9cbf" },
};
