export declare const VERSION: string;
export declare const DEFAULT_BASE_URL: string;
export type Method = "rembg" | "grabcut" | "ai";
export type ImageInput = Blob | ArrayBuffer | Uint8Array;
export interface Point { x: number; y: number; label: 0 | 1 }
export interface Detection {
  label: string | null; model: string | null; box: [number, number, number, number] | null;
  fg_points: number[][] | null; bg_points: number[][] | null; fallback: boolean; tried: Record<string, unknown>[];
}
export interface SegmentResponse {
  ok: true; version: string; method: Method; engine: string; rembg_model: string | null;
  width: number; height: number; elapsed_ms: number; image_png_b64: string; mask_png_b64: string | null;
  detection: Detection | null; image: Blob; mask: Blob | null;
}
export interface Subject { label: string; box_px: number[]; image_png_b64: string; image: Blob }
export interface MultiResponse {
  ok: true; version: string; method: "multi"; engine: string; width: number; height: number; elapsed_ms: number;
  subjects: Subject[]; detection: Detection;
}
export interface CommonOptions { rembgModel?: string; complete?: boolean; smooth?: number; despeckle?: boolean; whiteBorder?: boolean }
export interface SegmentOptions extends CommonOptions {
  method?: Method;
  /** normalized 0..1; tuples are [x, y, label] */
  points?: (Point | [number, number, (0 | 1)?])[];
  /** [x, y, w, h] normalized 0..1 */
  rect?: [number, number, number, number];
}
export declare class SegImageError extends Error { status: number; code: string; detail: string; /** seconds from Retry-After when status is 429 (rate limited) */ retryAfter?: number | null }
export declare class SegImage {
  constructor(baseUrl?: string, opts?: { timeoutMs?: number; fetch?: typeof fetch });
  health(): Promise<Record<string, any>>;
  models(): Promise<Record<string, any>>;
  segment(image: ImageInput, opts?: SegmentOptions): Promise<SegmentResponse>;
  multi(image: ImageInput, opts?: CommonOptions): Promise<MultiResponse>;
}
export default SegImage;
