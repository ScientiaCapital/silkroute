/**
 * Budget governance types.
 *
 * Ported from: src/silkroute/config/settings.py (BudgetConfig)
 *              src/silkroute/agent/cost_guard.py (BudgetCheck)
 */

export interface BudgetConfig {
  /** Hard monthly budget cap in USD. */
  monthlyMaxUsd: number;
  /** Daily budget pacing cap. */
  dailyMaxUsd: number;
  /** Slack alert at this fraction of budget (default 0.50). */
  alertThresholdWarning: number;
  /** Slack alert at this fraction (default 0.80). */
  alertThresholdCritical: number;
  /** Hard stop at this fraction (default 1.00). */
  alertThresholdShutdown: number;
  /** Default per-project monthly budget ($200 / 70 repos). */
  defaultProjectBudgetUsd: number;
  /** Slack webhook URL for budget alerts. */
  slackWebhookUrl: string;
  /** Telegram bot token for alerts. */
  telegramBotToken: string;
  /** Telegram chat ID for alerts. */
  telegramChatId: string;
}

export const DEFAULT_BUDGET_CONFIG: BudgetConfig = {
  monthlyMaxUsd: 200.0,
  dailyMaxUsd: 10.0,
  alertThresholdWarning: 0.5,
  alertThresholdCritical: 0.8,
  alertThresholdShutdown: 1.0,
  defaultProjectBudgetUsd: 2.85,
  slackWebhookUrl: "",
  telegramBotToken: "",
  telegramChatId: "",
};

export interface BudgetCheck {
  allowed: boolean;
  remainingUsd: number;
  spentUsd: number;
  limitUsd: number;
  warning: string;
}

export interface CostLogEntry {
  projectId: string;
  modelId: string;
  modelTier: string;
  provider: string;
  inputTokens: number;
  outputTokens: number;
  costUsd: number;
  sessionId: string;
}
