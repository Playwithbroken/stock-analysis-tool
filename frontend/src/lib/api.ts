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
        if (RETRYABLE_STATUS.has(response.status) && attempt < retries) {
          await sleep(retryDelayMs * (attempt + 1));
          continue;
        }
        throw new Error(`Request failed with status ${response.status}`);
      }
      return (await response.json()) as T;
    } catch (error) {
      lastError = error instanceof Error ? error : new Error("Request failed");
      if (attempt < retries) {
        await sleep(retryDelayMs * (attempt + 1));
        continue;
      }
    }
  }

  throw lastError || new Error("Request failed");
}
