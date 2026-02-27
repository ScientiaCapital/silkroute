/**
 * SilkRoute main extension — wires together pi-china-router + pi-budget-guard.
 *
 * This is the auto-discovered extension that pi loads from .pi/extensions/.
 * It re-exports both sub-extensions so they register their hooks and commands.
 */

// Import and re-register both extensions
import chinaRouter from "../../packages/pi-china-router/src/extension.js";
import budgetGuard from "../../packages/pi-budget-guard/src/extension.js";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export default function register(pi: any): void {
  chinaRouter(pi);
  budgetGuard(pi);
}
