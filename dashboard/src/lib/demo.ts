// Static fixtures for the AV/Edge demo page — the "OpenAV" story made tangible.
// Pure data, no backend: an edge-hosted open-weight model answers a plain-English
// AV question by driving an Epiphan Pearl over MCP, with zero cloud inference.
// Mirrors the canned Pearl-2-Room320B narrative in demo/mock_epiphan_mcp.py.

export interface PipelineStage {
  id: string;
  step: string;
  label: string;
  sublabel: string;
  icon: string;
  detail: string;
  meta: string;
}

// Left-to-right flow: edge model → orchestrator → MCP → device.
export const PIPELINE: PipelineStage[] = [
  {
    id: "model",
    step: "01",
    label: "Edge Model",
    sublabel: "Qwen2.5 · Ollama",
    icon: "🧠",
    detail: "Open-weight LLM running locally on the edge box — no cloud inference, no API key.",
    meta: "local · $0.00",
  },
  {
    id: "orchestrator",
    step: "02",
    label: "SilkRoute",
    sublabel: "Orchestrator + Router",
    icon: "🛤️",
    detail: "Routes the task by cost + hardware fit, then calls tools in a ReAct loop.",
    meta: "tier: free · local",
  },
  {
    id: "mcp",
    step: "03",
    label: "MCP",
    sublabel: "Model Context Protocol",
    icon: "🔌",
    detail: "The same open protocol Claude Desktop & Cursor speak — model and device stay swappable.",
    meta: "get_recording_status",
  },
  {
    id: "device",
    step: "04",
    label: "Pearl-2",
    sublabel: "Room 320-B",
    icon: "🎥",
    detail: "Epiphan encoder/switcher answers over MCP — real device control, vendor-neutral.",
    meta: "● recording",
  },
];

export interface PearlDeviceState {
  name: string;
  model: string;
  room: string;
  firmware: string;
  recorderName: string;
  state: "recording" | "stopped" | "paused";
  durationLabel: string;
  filename: string;
  inputSignal: string;
}

export const PEARL: PearlDeviceState = {
  name: "Pearl-2-Room320B",
  model: "Pearl-2",
  room: "Room 320-B",
  firmware: "4.14.2",
  recorderName: "Room 320-B Recorder",
  state: "recording",
  durationLabel: "30:00",
  filename: "room_320b_2026-07-12_09-00-00.mp4",
  inputSignal: "HDMI 1 · 1920×1080 · 60fps",
};

export interface DemoTurn {
  role: "user" | "agent" | "tool";
  text: string;
}

export const CONVERSATION: DemoTurn[] = [
  { role: "user", text: "did recording start in room 320-B" },
  { role: "tool", text: "→ MCP call: get_recording_status()" },
  {
    role: "agent",
    text:
      "Yes — Room 320-B is recording. The Pearl-2 recorder has been capturing " +
      "for 30 minutes to room_320b_2026-07-12_09-00-00.mp4, with a live HDMI 1 " +
      "signal at 1080p60.",
  },
];

// Headline stats for the demo hero.
export const DEMO_META = {
  model: "ollama/qwen2.5:14b",
  inferenceCost: "$0.00",
  cloudCalls: 0,
  protocol: "MCP (stdio)",
};
