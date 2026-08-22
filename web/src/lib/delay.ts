export const MIN_STEP_DELAY_MS = 400;

export function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
