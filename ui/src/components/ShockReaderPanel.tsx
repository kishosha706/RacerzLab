import type { ShockReaderResponse } from "../types/shockReader";

type ShockReaderPanelProps = {
  data: ShockReaderResponse | null;
  loading: boolean;
  error?: string | null;
};

export function ShockReaderPanel(_props: ShockReaderPanelProps) {
  return null;
}
