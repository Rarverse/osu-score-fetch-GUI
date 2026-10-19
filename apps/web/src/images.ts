// Page artwork and canvas exports share the same browser/server image cache.
export function imageUrl(url: string | null): string {
  return url ? `/api/v1/images?url=${encodeURIComponent(url)}` : "";
}
