/* ──────────────────────────────────────────────────────────────
   NotInTelegram.tsx — экран-заглушка при открытии вне Telegram
   ────────────────────────────────────────────────────────────── */
import { Smartphone } from "lucide-react";

export default function NotInTelegram() {
  return (
    <div
      className="flex flex-col items-center justify-center min-h-screen gap-6 p-8 text-center"
      style={{ backgroundColor: "var(--bg-primary)", color: "var(--text-primary)" }}
    >
      <div
        className="w-20 h-20 rounded-2xl flex items-center justify-center"
        style={{ backgroundColor: "var(--bg-secondary)" }}
      >
        <Smartphone size={40} style={{ color: "var(--accent)" }} />
      </div>

      <div className="space-y-2">
        <h1 className="text-xl font-bold">Откройте в Telegram</h1>
        <p className="text-sm" style={{ color: "var(--text-hint)", maxWidth: "280px" }}>
          Это приложение работает только внутри Telegram Mini App.
          Пожалуйста, запустите его через бота.
        </p>
      </div>

      <a
        href="https://t.me/IIIPredvestnikIIIBot"
        className="px-6 py-3 rounded-xl font-semibold text-sm transition-opacity active:opacity-70"
        style={{ backgroundColor: "var(--accent)", color: "#ffffff" }}
      >
        Открыть бота
      </a>
    </div>
  );
}
