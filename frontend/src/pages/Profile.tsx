/* ──────────────────────────────────────────────────────────────
   Profile.tsx — Профиль пользователя
   Баланс · XP · VIP · Питомец · Партнёр · Облигации
   ────────────────────────────────────────────────────────────── */
import { useEffect, useState } from "react";
import { Coins, Star, Heart, PawPrint, TrendingUp } from "lucide-react";
import { fetchUserData } from "../lib/api";
import type { UserData } from "../types";

interface Props {
  userId: number;
}

export default function Profile({ userId }: Props) {
  const [data, setData] = useState<UserData | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!userId) return;
    fetchUserData(userId)
      .then(setData)
      .catch((e: Error) => setError(e.message));
  }, [userId]);

  if (error) {
    return <ErrorBox message={error} />;
  }
  if (!data) {
    return <ProfileSkeleton />;
  }

  const level = Math.floor(data.xp / 1000);

  return (
    <div className="animate-fadeIn p-4 space-y-4">
      {/* ── Шапка ──────────────────────────────── */}
      <header className="flex items-center gap-3">
        <div
          className="w-14 h-14 rounded-full flex items-center justify-center text-2xl font-bold shrink-0"
          style={{ backgroundColor: "var(--bg-secondary)", color: "var(--accent)" }}
        >
          {data.name.charAt(0).toUpperCase()}
        </div>
        <div className="min-w-0">
          <h1 className="text-lg font-semibold truncate">{data.name}</h1>
          <div className="flex items-center gap-2 text-sm" style={{ color: "var(--text-hint)" }}>
            <span>Ур. {level}</span>
            {data.vip && (
              <span
                className="px-1.5 py-0.5 rounded text-[10px] font-bold"
                style={{ backgroundColor: "var(--accent)", color: "var(--accent-text)" }}
              >
                VIP
              </span>
            )}
          </div>
        </div>
      </header>

      {/* ── Баланс / XP ───────────────────────── */}
      <div className="grid grid-cols-2 gap-3">
        <StatCard icon={<Coins size={18} />} label="Баланс" value={fmt(data.balance)} />
        <StatCard icon={<Star size={18} />} label="XP" value={fmt(data.xp)} />
      </div>

      {/* ── Питомец ────────────────────────────── */}
      {data.pet && (
        <Card>
          <div className="flex items-center gap-2">
            <PawPrint size={18} style={{ color: "var(--accent)" }} />
            <span className="font-medium">Питомец</span>
          </div>
          <p className="mt-1 text-sm" style={{ color: "var(--text-hint)" }}>
            {data.pet.emoji} {data.pet.name} ({data.pet.type}) · Усталость: {data.pet.fatigue}%
          </p>
        </Card>
      )}

      {/* ── Партнёр ────────────────────────────── */}
      {data.partner && (
        <Card>
          <div className="flex items-center gap-2">
            <Heart size={18} style={{ color: "#e84393" }} />
            <span className="font-medium">Партнёр</span>
          </div>
          <p className="mt-1 text-sm" style={{ color: "var(--text-hint)" }}>
            {data.partner.partner_name} · с {new Date(data.partner.married_at).toLocaleDateString()}
          </p>
        </Card>
      )}

      {/* ── Облигации ──────────────────────────── */}
      {data.bonds.length > 0 && (
        <Card>
          <div className="flex items-center gap-2 mb-2">
            <TrendingUp size={18} style={{ color: "var(--accent)" }} />
            <span className="font-medium">Облигации</span>
          </div>
          <div className="space-y-1">
            {data.bonds.map((b) => (
              <div key={b.name} className="flex justify-between text-sm">
                <span>{b.name} ×{b.amount}</span>
                <span style={{ color: "var(--text-hint)" }}>{fmt(b.value)} 🪙</span>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}

/* ── Вспомогательные компоненты ───────────────────────────────── */

function StatCard({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div
      className="rounded-xl p-3 flex flex-col gap-1"
      style={{ backgroundColor: "var(--bg-secondary)" }}
    >
      <div className="flex items-center gap-1.5 text-xs" style={{ color: "var(--text-hint)" }}>
        {icon}
        {label}
      </div>
      <span className="text-xl font-bold">{value}</span>
    </div>
  );
}

function Card({ children }: { children: React.ReactNode }) {
  return (
    <div
      className="rounded-xl p-3"
      style={{ backgroundColor: "var(--bg-secondary)" }}
    >
      {children}
    </div>
  );
}

function ErrorBox({ message }: { message: string }) {
  return (
    <div className="p-4 text-center" style={{ color: "#e74c3c" }}>
      <p className="font-medium">Ошибка</p>
      <p className="text-sm mt-1">{message}</p>
    </div>
  );
}

function ProfileSkeleton() {
  return (
    <div className="p-4 space-y-4 animate-pulse">
      <div className="flex items-center gap-3">
        <div className="skeleton w-14 h-14 rounded-full" />
        <div className="space-y-2 flex-1">
          <div className="skeleton h-4 w-32 rounded" />
          <div className="skeleton h-3 w-20 rounded" />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="skeleton h-20 rounded-xl" />
        <div className="skeleton h-20 rounded-xl" />
      </div>
    </div>
  );
}

function fmt(n: number): string {
  return n.toLocaleString("ru-RU");
}
