/* ──────────────────────────────────────────────────────────────
   ProfileAvatar — аватарка с CSS-рамкой профиля.
   Использует /api/proxy/avatar для обхода CORS и кэширования.
   ────────────────────────────────────────────────────────────── */
import { useState } from "react";
import { User } from "lucide-react";

const FRAME_KEYS = [
  "warrior", "moon", "fire", "star", "diamond",
  "champion", "sakura", "abyss", "premium",
  "bronze", "silver", "copper", "stone", "wood", "king",
  "ocean", "forest", "crystal", "thunder", "fatui",
  "angel", "celestia", "phoenix", "dragon", "void", "galaxy",
  "divine", "rainbow", "cosmic", "mythic",
  "dark_matter_frame", "herald_frame", "first_topup",
] as const;

export type FrameKey = (typeof FRAME_KEYS)[number] | string | null | undefined;

interface Props {
  /** Оригинальный URL аватарки из Telegram / профиля */
  src?: string | null;
  /** Ключ рамки (из гачи / магазина) */
  frame?: FrameKey;
  /** Размер в пикселях (квадрат) */
  size?: number;
  className?: string;
  /** alt-текст */
  alt?: string;
}

/** Проксируем через наш бэкенд чтобы избежать CORS / протухших URL */
function proxyUrl(raw?: string | null): string | null {
  if (!raw) return null;
  // Уже наш прокси — не оборачиваем дважды
  if (raw.startsWith("/api/proxy/avatar")) return raw;
  return `/api/proxy/avatar?url=${encodeURIComponent(raw)}`;
}

export default function ProfileAvatar({ src, frame, size = 56, className = "", alt = "Avatar" }: Props) {
  const [errored, setErrored] = useState(false);
  const url = proxyUrl(src);
  const frameClass = frame ? `avatar-frame-wrap frame-${frame}` : "avatar-frame-wrap";

  const style = { width: size, height: size, minWidth: size, minHeight: size };

  return (
    <span className={`${frameClass} ${className}`} style={style}>
      {url && !errored ? (
        <img
          src={url}
          alt={alt}
          width={size}
          height={size}
          style={{ width: size, height: size }}
          onError={() => setErrored(true)}
          loading="lazy"
        />
      ) : (
        <span
          className="avatar-placeholder flex items-center justify-center rounded-full"
          style={{ width: size, height: size, backgroundColor: "var(--bg-secondary)" }}
        >
          <User size={Math.round(size * 0.45)} style={{ color: "var(--text-hint)" }} />
        </span>
      )}
    </span>
  );
}
