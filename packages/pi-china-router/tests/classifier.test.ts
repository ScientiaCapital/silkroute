/**
 * Tests for keyword-based task classification.
 *
 * Ported from: tests/test_classifier.py
 */

import { describe, expect, it } from "vitest";
import { classifyTask } from "../src/classifier.js";
import { Capability, ModelTier } from "../src/types.js";

describe("classifyTask", () => {
  // ─── Premium tier triggers ────────────────────────────────────────
  it("classifies security review as PREMIUM", () => {
    const result = classifyTask("security review this codebase");
    expect(result.tier).toBe(ModelTier.PREMIUM);
    expect(result.confidence).toBe(0.8);
    expect(result.reason).toContain("security review");
  });

  it("classifies security audit as PREMIUM", () => {
    const result = classifyTask("run a security audit on auth module");
    expect(result.tier).toBe(ModelTier.PREMIUM);
  });

  it("classifies architecture tasks as PREMIUM", () => {
    const result = classifyTask("architect a new microservice");
    expect(result.tier).toBe(ModelTier.PREMIUM);
  });

  it("classifies migration plan as PREMIUM", () => {
    const result = classifyTask("create a migration plan for the database");
    expect(result.tier).toBe(ModelTier.PREMIUM);
  });

  it("classifies codebase refactor as PREMIUM", () => {
    const result = classifyTask("codebase refactor from monolith to services");
    expect(result.tier).toBe(ModelTier.PREMIUM);
  });

  // ─── Free tier triggers ───────────────────────────────────────────
  it("classifies summarize as FREE", () => {
    const result = classifyTask("summarize this file");
    expect(result.tier).toBe(ModelTier.FREE);
    expect(result.confidence).toBe(0.7);
  });

  it("classifies format as FREE", () => {
    const result = classifyTask("format this code");
    expect(result.tier).toBe(ModelTier.FREE);
  });

  it("classifies explain as FREE", () => {
    const result = classifyTask("explain what this function does");
    expect(result.tier).toBe(ModelTier.FREE);
  });

  it("classifies lint as FREE", () => {
    const result = classifyTask("lint the project");
    expect(result.tier).toBe(ModelTier.FREE);
  });

  it("classifies triage as FREE", () => {
    const result = classifyTask("triage these issues");
    expect(result.tier).toBe(ModelTier.FREE);
  });

  // ─── Standard tier triggers ───────────────────────────────────────
  it("classifies review as STANDARD", () => {
    const result = classifyTask("review this pull request");
    expect(result.tier).toBe(ModelTier.STANDARD);
    expect(result.confidence).toBe(0.7);
  });

  it("classifies implement as STANDARD", () => {
    const result = classifyTask("implement user authentication");
    expect(result.tier).toBe(ModelTier.STANDARD);
  });

  it("classifies fix bug as STANDARD", () => {
    const result = classifyTask("fix bug in the auth handler");
    expect(result.tier).toBe(ModelTier.STANDARD);
  });

  it("classifies build as STANDARD", () => {
    const result = classifyTask("build a REST API for users");
    expect(result.tier).toBe(ModelTier.STANDARD);
  });

  // ─── Default behavior ────────────────────────────────────────────
  it("defaults to STANDARD with low confidence for unknown tasks", () => {
    const result = classifyTask("do something");
    expect(result.tier).toBe(ModelTier.STANDARD);
    expect(result.confidence).toBe(0.4);
    expect(result.reason).toBe("default routing");
  });

  // ─── Capability detection ────────────────────────────────────────
  it("detects CODING capability", () => {
    const result = classifyTask("write a function to parse JSON");
    expect(result.capabilities).toContain(Capability.CODING);
  });

  it("detects REASONING capability", () => {
    const result = classifyTask("analyze why this test fails");
    expect(result.capabilities).toContain(Capability.REASONING);
  });

  it("detects TOOL_CALLING capability", () => {
    const result = classifyTask("run the test suite");
    expect(result.capabilities).toContain(Capability.TOOL_CALLING);
  });

  it("detects AGENTIC capability", () => {
    const result = classifyTask("automate the deployment pipeline");
    expect(result.capabilities).toContain(Capability.AGENTIC);
  });

  it("detects MATH capability", () => {
    const result = classifyTask("calculate the optimal batch size");
    expect(result.capabilities).toContain(Capability.MATH);
  });

  it("detects CREATIVE capability", () => {
    const result = classifyTask("generate a creative story about AI");
    expect(result.capabilities).toContain(Capability.CREATIVE);
  });

  it("detects multiple capabilities", () => {
    const result = classifyTask("debug and fix the broken build pipeline");
    expect(result.capabilities).toContain(Capability.REASONING);
    expect(result.capabilities).toContain(Capability.CODING);
  });

  it("defaults to CODING + TOOL_CALLING when no capabilities detected", () => {
    const result = classifyTask("hello");
    expect(result.capabilities).toEqual([Capability.CODING, Capability.TOOL_CALLING]);
  });

  // ─── Premium overrides standard triggers ──────────────────────────
  it("premium trigger overrides standard", () => {
    // "security review" is premium even though "review" alone is standard
    const result = classifyTask("security review the authentication module");
    expect(result.tier).toBe(ModelTier.PREMIUM);
  });
});
