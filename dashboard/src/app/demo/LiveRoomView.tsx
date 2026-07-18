"use client";

// Live layer for the AV/Edge demo. Streams a Think → Act → Observe agent trace
// from the API's SSE endpoint (GET /demo/stream) and the room's current state
// (GET /demo/room). Falls back to the static fixtures from @/lib/demo whenever
// the API is unreachable — so the page always renders (Vercel-safe), matching
// the try/catch-static-fallback convention used by the other dashboard pages.

import { useEffect, useRef, useState } from "react";
import { PEARL, CONVERSATION } from "@/lib/demo";
import type { RoomState, TraceEvent, HealEvent } from "@/lib/types";
import { HEAL_FAULTS } from "@/lib/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8787";

function fmtDuration(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

function str(data: Record<string, unknown>, key: string): string {
  const v = data[key];
  return typeof v === "string" ? v : "";
}

function LiveBadge({ live }: { live: boolean }) {
  return (
    <span
      className={
        "inline-flex items-center gap-1.5 text-[10px] uppercase tracking-wide px-2 py-0.5 rounded-full " +
        (live ? "text-emerald-400 bg-emerald-400/10" : "text-neutral-500 bg-neutral-800")
      }
      title={live ? "Streaming live from the API" : "API unreachable — showing static fixtures"}
    >
      {live && <span className="sr-rec-dot w-1.5 h-1.5 rounded-full bg-emerald-400" />}
      {live ? "live" : "static"}
    </span>
  );
}

// --- live trace panel ---

function TraceView({ trace }: { trace: TraceEvent[] }) {
  return (
    <div className="flex flex-col gap-4">
      {trace.map((ev, i) => {
        if (ev.type === "session_start") {
          return (
            <div key={i}>
              <p className="text-xs uppercase tracking-wide text-neutral-600 mb-1">You</p>
              <p className="text-neutral-200">{str(ev.data, "task")}</p>
            </div>
          );
        }
        if (ev.type === "thought") {
          return (
            <p key={i} className="text-xs text-neutral-500 italic pl-1 border-l border-neutral-800">
              {str(ev.data, "text")}
            </p>
          );
        }
        if (ev.type === "tool_call") {
          return (
            <p key={i} className="font-mono text-xs text-amber-400/80 pl-1">
              → MCP call: {str(ev.data, "tool_name")}()
              {ev.data["success"] === true && <span className="text-emerald-400/70"> ✓</span>}
            </p>
          );
        }
        if (ev.type === "answer") {
          return (
            <div key={i} className="border-l-2 border-amber-500/40 pl-3">
              <p className="text-xs uppercase tracking-wide text-neutral-600 mb-1">SilkRoute</p>
              <p className="text-neutral-300 leading-relaxed">{str(ev.data, "text")}</p>
            </div>
          );
        }
        return null;
      })}
    </div>
  );
}

function StaticTrace() {
  return (
    <div className="flex flex-col gap-4">
      {CONVERSATION.map((turn, i) => {
        if (turn.role === "tool") {
          return (
            <p key={i} className="font-mono text-xs text-amber-400/80 pl-1">
              {turn.text}
            </p>
          );
        }
        const isUser = turn.role === "user";
        return (
          <div key={i} className={isUser ? "" : "border-l-2 border-amber-500/40 pl-3"}>
            <p className="text-xs uppercase tracking-wide text-neutral-600 mb-1">
              {isUser ? "You" : "SilkRoute"}
            </p>
            <p className={isUser ? "text-neutral-200" : "text-neutral-300 leading-relaxed"}>
              {turn.text}
            </p>
          </div>
        );
      })}
    </div>
  );
}

// --- device status panel ---

function DeviceRow({ label, children, wide }: { label: string; children: React.ReactNode; wide?: boolean }) {
  return (
    <div className={wide ? "col-span-2" : ""}>
      <dt className="text-neutral-500 text-xs">{label}</dt>
      <dd className="font-mono text-neutral-300">{children}</dd>
    </div>
  );
}

function DeviceStatus({ room }: { room: RoomState | null }) {
  const isLive = room !== null;
  const recorderState = isLive ? room.recorder_state : PEARL.state;
  const recording = recorderState === "recording";
  const name = isLive ? room.device_name : PEARL.name;
  const model = isLive ? room.model : PEARL.model;
  const firmware = isLive ? room.firmware : PEARL.firmware;
  const recorderName = isLive ? room.recorder_name : PEARL.recorderName;
  const duration = isLive ? fmtDuration(room.duration_seconds) : PEARL.durationLabel;
  const filename = isLive ? room.filename : PEARL.filename;
  const roomLabel = isLive ? room.device_name.replace("Pearl-2-", "Room ").replace("Room320B", "320-B") : PEARL.room;

  return (
    <div className="sr-fade-up bg-neutral-900 border border-neutral-800 rounded-xl p-6" style={{ animationDelay: "560ms" }}>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold">{roomLabel}</h2>
        <span
          className={
            "inline-flex items-center gap-2 text-xs px-2.5 py-1 rounded-full " +
            (recording ? "text-amber-400 bg-amber-400/10" : "text-neutral-400 bg-neutral-800")
          }
        >
          {recording && <span className="sr-rec-dot w-2 h-2 rounded-full bg-amber-400" />}
          {recorderState}
        </span>
      </div>
      <dl className="grid grid-cols-2 gap-y-4 gap-x-4 text-sm">
        <DeviceRow label="Device">{name}</DeviceRow>
        <DeviceRow label="Model · FW">{model} · {firmware}</DeviceRow>
        <DeviceRow label="Recorder">{recorderName}</DeviceRow>
        <DeviceRow label="Duration">{duration}</DeviceRow>
        <DeviceRow label="File" wide>
          <span className="break-all">{filename}</span>
        </DeviceRow>
        {isLive ? (
          <DeviceRow label="Fleet" wide>
            {room.devices_online}/{room.devices_total} online · {room.recorders_active} recording ·
            CPU {room.cpu_percent}% · {(room.storage_free_bytes / 1e9).toFixed(0)}GB free
          </DeviceRow>
        ) : (
          <DeviceRow label="Input signal" wide>
            {PEARL.inputSignal}
          </DeviceRow>
        )}
      </dl>
    </div>
  );
}

export default function LiveRoomView() {
  const [room, setRoom] = useState<RoomState | null>(null);
  const [trace, setTrace] = useState<TraceEvent[]>([]);
  const [live, setLive] = useState(false);
  const startedRef = useRef(false);

  useEffect(() => {
    if (startedRef.current) return; // guard against React 18 StrictMode double-invoke
    startedRef.current = true;

    let cancelled = false;

    fetch(`${API_BASE}/demo/room`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((data: RoomState) => {
        if (!cancelled) {
          setRoom(data);
          setLive(true);
        }
      })
      .catch(() => {
        /* API unreachable — keep static fallback */
      });

    const es = new EventSource(`${API_BASE}/demo/stream`);
    es.onmessage = (event) => {
      if (event.data.startsWith("[")) {
        // [DONE] or [ERROR ...] — terminal frame
        es.close();
        return;
      }
      try {
        const parsed: TraceEvent = JSON.parse(event.data);
        if (!cancelled) {
          setTrace((prev) => [...prev, parsed]);
          setLive(true);
        }
      } catch {
        /* ignore malformed frame */
      }
    };
    es.onerror = () => es.close();

    return () => {
      cancelled = true;
      es.close();
    };
  }, []);

  return (
    <>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="sr-fade-up bg-neutral-900 border border-neutral-800 rounded-xl p-6" style={{ animationDelay: "480ms" }}>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold">What the agent did</h2>
            <LiveBadge live={live} />
          </div>
          {trace.length > 0 ? <TraceView trace={trace} /> : <StaticTrace />}
        </div>

        <DeviceStatus room={room} />
      </div>

      <SelfHealPanel />
    </>
  );
}

// --- self-healing panel: inject a fault → watch the room heal itself ---

const FAULT_LABELS: Record<string, string> = {
  recorder_stopped: "Recorder stopped",
  signal_loss: "Input signal lost",
  storage_full: "Storage full",
  storage_unmounted: "Storage unmounted",
  device_offline: "Device offline",
  cpu_overload: "CPU overload",
};

function SelfHealPanel() {
  const [fault, setFault] = useState<string>("signal_loss");
  const [steps, setSteps] = useState<string[]>([]);
  const [outcome, setOutcome] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const esRef = useRef<EventSource | null>(null);

  const inject = () => {
    esRef.current?.close();
    setSteps([]);
    setOutcome(null);
    setRunning(true);

    const es = new EventSource(`${API_BASE}/demo/heal?fault=${fault}`);
    esRef.current = es;
    es.onmessage = (event) => {
      if (event.data.startsWith("[")) {
        es.close();
        setRunning(false);
        return;
      }
      try {
        const ev: HealEvent = JSON.parse(event.data);
        if (ev.type === "heal_step") {
          setSteps((prev) => [...prev, str(ev.data, "text")]);
        } else if (ev.type === "heal_result") {
          setOutcome(str(ev.data, "outcome"));
        }
      } catch {
        /* ignore malformed frame */
      }
    };
    es.onerror = () => {
      es.close();
      setRunning(false);
    };
  };

  useEffect(() => () => esRef.current?.close(), []);

  const outcomeStyle =
    outcome === "healed"
      ? "text-emerald-400 bg-emerald-400/10"
      : outcome === "unhandled"
        ? "text-amber-400 bg-amber-400/10"
        : "text-neutral-400 bg-neutral-800";
  const outcomeLabel =
    outcome === "healed"
      ? "✓ Healed autonomously"
      : outcome === "unhandled"
        ? "⚠ Unhandled — evolve the playbook"
        : outcome === "healthy"
          ? "Already healthy"
          : "";

  return (
    <div className="sr-fade-up bg-neutral-900 border border-neutral-800 rounded-xl p-6 mt-6" style={{ animationDelay: "640ms" }}>
      <div className="flex items-center justify-between mb-1">
        <h2 className="text-lg font-semibold">Self-healing loop</h2>
        <span className="text-[10px] uppercase tracking-wide text-neutral-500">detect → fix → verify</span>
      </div>
      <p className="text-xs text-neutral-500 mb-4">
        Inject a fault into the room. The control plane detects it, picks a remediation from the
        playbook, calls the device action over MCP, and re-reads to verify.
      </p>

      <div className="flex flex-wrap items-center gap-3 mb-5">
        <select
          value={fault}
          onChange={(e) => setFault(e.target.value)}
          disabled={running}
          className="bg-neutral-800 border border-neutral-700 rounded-lg px-3 py-2 text-sm text-neutral-200 focus:outline-none focus:border-neutral-500 disabled:opacity-50"
        >
          {HEAL_FAULTS.map((f) => (
            <option key={f} value={f}>
              {FAULT_LABELS[f] ?? f}
            </option>
          ))}
        </select>
        <button
          onClick={inject}
          disabled={running}
          className="bg-amber-500 hover:bg-amber-400 disabled:opacity-50 text-neutral-950 font-medium text-sm px-4 py-2 rounded-lg transition-colors"
        >
          {running ? "Healing…" : "Inject fault → Heal"}
        </button>
        {outcome && (
          <span className={"text-xs px-2.5 py-1 rounded-full " + outcomeStyle}>{outcomeLabel}</span>
        )}
      </div>

      {steps.length > 0 && (
        <ol className="flex flex-col gap-2">
          {steps.map((s, i) => (
            <li key={i} className="font-mono text-xs text-neutral-400 pl-1 border-l border-neutral-800">
              {s}
            </li>
          ))}
        </ol>
      )}
      {steps.length === 0 && !running && (
        <p className="text-xs text-neutral-600 italic">
          Requires the API (<span className="font-mono">/demo/heal</span>) — pick a fault and click to run the loop live.
        </p>
      )}
    </div>
  );
}
