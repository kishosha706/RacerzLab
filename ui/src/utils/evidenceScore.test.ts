import { describe, expect, it } from "vitest";
import { evidenceStrengthLabel, evidenceStrengthOutOf100 } from "./evidenceScore";

describe("ordinal evidence score formatting", () => {
  it("uses an ordinal out-of-100 scale rather than probability wording", () => {
    expect(evidenceStrengthOutOf100(0.724)).toBe("72/100");
    expect(evidenceStrengthLabel(0.724)).toBe("Evidence strength 72/100");
    expect(evidenceStrengthLabel(0.724)).not.toContain("%");
    expect(evidenceStrengthLabel(0.724).toLowerCase()).not.toContain("confidence");
  });

  it("fails closed for unavailable and bounds malformed scores", () => {
    expect(evidenceStrengthOutOf100(null)).toBe("Unavailable");
    expect(evidenceStrengthOutOf100(Number.NaN)).toBe("Unavailable");
    expect(evidenceStrengthOutOf100(2)).toBe("100/100");
    expect(evidenceStrengthOutOf100(-1)).toBe("0/100");
  });
});
