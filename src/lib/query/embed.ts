/**
 * Local query embeddings — server-side only (Node runtime, via
 * @huggingface/transformers' ONNX build of the same model used at ingestion
 * time: Xenova/all-MiniLM-L6-v2, 384-dim). Verified numerically equivalent
 * to the Python sentence-transformers output used to embed the corpus
 * (scripts/ingest_documents.py) — same model checkpoint, same pooling
 * (mean) and normalization (L2), so query and corpus vectors share one
 * space without re-embedding anything.
 *
 * Never imported from client code — this only runs inside TanStack Start
 * server functions (see src/lib/chat-api.ts), matching how the timetable
 * API keeps Supabase credentials server-side only.
 */

import { pipeline, type FeatureExtractionPipeline } from "@huggingface/transformers";

let extractorPromise: Promise<FeatureExtractionPipeline> | null = null;

function getExtractor(): Promise<FeatureExtractionPipeline> {
  if (!extractorPromise) {
    extractorPromise = pipeline("feature-extraction", "Xenova/all-MiniLM-L6-v2") as Promise<FeatureExtractionPipeline>;
  }
  return extractorPromise;
}

export async function embedQuery(text: string): Promise<number[]> {
  const extractor = await getExtractor();
  const output = await extractor(text, { pooling: "mean", normalize: true });
  return Array.from(output.data as Float32Array);
}
