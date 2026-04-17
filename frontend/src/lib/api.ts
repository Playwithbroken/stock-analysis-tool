const RETRYABLE_STATUS = new Set([502, 503, 504]);

function sleep(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

export async function fetchJsonWithRetry<T>(
  input: RequestInfo | URL,
  init?: RequestInit,
  options?: { retries?: number; retryDelayMs?: number },
): Promise<T> {
  const retries = options?.retries ?? 2;
  const retryDelayMs = options?.retryDelayMs ?? 900;

  let lastError: Error | null = null;

  for (let attempt = 0; attempt <= retries; attempt += 1) {
    try {
      const response = await fetch(input, init);
      if (!response.ok) {
        let detail = "";
        try {
          const payload = await response.json();
          detail = payload?.detail || payload?.message || "";
        } catch {
          try {
            detail = await response.text();
          } catch {
            detail = "";
          }
        }
        if (RETRYABLE_STATUS.has(response.status) && attempt < retries) {
          await sleep(retryDelayMs * (attempt + 1));
          continue;
        }
        const error = new Error(
          detail
            ? `Request failed with status ${response.status}: ${detail}`
            : `Request failed with status ${response.status}`,
        );
        (error as Error & { status?: number }).status = response.status;
        throw error;
      }
      return (await response.json()) as T;
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        throw error;
      }
      lastError = error instanceof Error ? error : new Error("Request failed");
      if (attempt < retries) {
        await sleep(retryDelayMs * (attempt + 1));
        continue;
      }
    }
  }

  throw lastError || new Error("Request failed");
}
