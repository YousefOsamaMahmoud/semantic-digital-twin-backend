// ============================================================
// data/constants.js — Static UI Configuration
//
// Navigation items and page titles are static app config,
// NOT mock data. They are defined here so mockData.js can
// be fully removed once migration is complete.
// ============================================================

import { C } from "../styles/theme";

export const NAV = [
  { id: "dashboard",  label: "Dashboard",       icon: "◈", dot: C.orange },
  { id: "sla",        label: "SLA Upload",       icon: "◉", dot: C.purple },
  { id: "inventory",  label: "Inventory Risk",   icon: "⬢", dot: C.red    },
  { id: "suppliers",  label: "Suppliers",        icon: "◎", dot: C.green  },
  { id: "violations", label: "SLA Violations",   icon: "◆", dot: C.orange },
  { id: "ai",         label: "AI Assistant",     icon: "◑", dot: C.purple },
  { id: "alerts",     label: "Alerts",           icon: "🔔", dot: C.red    },
];

export const PAGE_TITLES = {
  dashboard:  "Dashboard · Mission Control",
  sla:        "SLA Upload · LLM Parser",
  inventory:  "Inventory Risk · Traffic Light",
  suppliers:  "Suppliers · Directory",
  violations: "SLA Violations · Penalty Calculator",
  ai:         "AI Assistant · Natural Language Query",
  alerts:     "Alerts · Notifications Center",
};
