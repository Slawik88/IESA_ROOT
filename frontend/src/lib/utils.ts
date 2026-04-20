/** Извлекает человекочитаемое сообщение об ошибке из API-ответа.
 *  Бэкенд выбрасывает: Error("API 400: {\"error\": \"...\"}") */
export function extractApiError(e: unknown): string {
  if (!(e instanceof Error)) return "Ошибка";
  const match = e.message.match(/API \d+: (.*)/s);
  if (match) {
    try { return (JSON.parse(match[1]) as { error?: string }).error ?? match[1]; }
    catch { return match[1]; }
  }
  return e.message;
}
