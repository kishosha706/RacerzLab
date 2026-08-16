type CanonicalJsonOptions = {
  /** Object keys whose JSON numbers originated from Python float fields. */
  pythonFloatKeys?: ReadonlySet<string>;
};

function pythonFloat(value: number): string {
  if (!Number.isFinite(value)) throw new TypeError("Canonical JSON rejects non-finite numbers.");
  if (Object.is(value, -0)) return "-0.0";
  const magnitude = Math.abs(value);
  if (magnitude !== 0 && (magnitude < 1e-4 || magnitude >= 1e16)) {
    const [mantissa, rawExponent] = value.toExponential().split("e");
    const exponent = Number(rawExponent);
    const sign = exponent >= 0 ? "+" : "-";
    return `${mantissa}e${sign}${Math.abs(exponent).toString().padStart(2, "0")}`;
  }
  const encoded = value.toString();
  return Number.isInteger(value) ? `${encoded}.0` : encoded;
}

function canonicalJson(value: unknown, options: CanonicalJsonOptions, key?: string): string {
  if (typeof value === "number" && key && options.pythonFloatKeys?.has(key)) {
    return pythonFloat(value);
  }
  if (value === null || typeof value === "boolean" || typeof value === "number" || typeof value === "string") {
    const encoded = JSON.stringify(value) as string;
    return encoded.replace(/[^\x00-\x7f]/g, (character) => (
      `\\u${character.charCodeAt(0).toString(16).padStart(4, "0")}`
    ));
  }
  if (Array.isArray(value)) {
    return `[${value.map((item) => canonicalJson(item, options, key)).join(",")}]`;
  }
  if (typeof value === "object") {
    const record = value as Record<string, unknown>;
    return `{${Object.keys(record).sort().map((itemKey) => `${JSON.stringify(itemKey)}:${canonicalJson(record[itemKey], options, itemKey)}`).join(",")}}`;
  }
  throw new TypeError("Canonical JSON accepts only JSON values.");
}

export async function canonicalJsonSha256(
  value: unknown,
  options: CanonicalJsonOptions = {},
): Promise<string> {
  const bytes = new TextEncoder().encode(canonicalJson(value, options));
  const digest = await globalThis.crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}
