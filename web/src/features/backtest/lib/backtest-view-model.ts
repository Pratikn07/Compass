import type {
  BacktestLearningReport,
  BacktestSetup,
} from "@/features/backtest/lib/backtest-report.schema";

export type MetricTone = "danger" | "muted" | "success" | "warning";

export type BacktestMetric = {
  detail: string;
  id:
    | "beatsBuyHold"
    | "maxDrawdown"
    | "sharpe"
    | "totalReturn"
    | "winRate";
  label: string;
  tone: MetricTone;
  value: string;
};

export type EquityCurvePoint = {
  buyHoldEquity: number;
  date: string;
  label: string;
  strategyEquity: number;
};

export type ReturnComparisonPoint = {
  label: "Buy and hold" | "Excess" | "Strategy";
  value: number;
};

export type OutcomeDistributionPoint = {
  count: number;
  label: "Flat" | "Loss" | "Not evaluable" | "Win";
};

export type SetupRow = {
  benchmarkReturn: string;
  entryDate: string;
  exitDate: string;
  expression: string;
  netPnl: string;
  outcome: string;
  setupId: string;
  status: string;
  target: string;
  theme: string;
  warningCount: number;
};

export type BacktestViewModel = {
  diagnostics: {
    excluded: { count: number; label: string }[];
    warnings: string[];
  };
  equityCurve: EquityCurvePoint[];
  metrics: BacktestMetric[];
  metadata: {
    createdAt: string;
    reportDate: string;
    runId: string;
    target: string;
    theme: string;
  };
  outcomeDistribution: OutcomeDistributionPoint[];
  returnComparison: ReturnComparisonPoint[];
  setupRows: SetupRow[];
};

const UNAVAILABLE = "Unavailable";

export function buildBacktestViewModel(
  report: BacktestLearningReport,
): BacktestViewModel {
  const summary = report.payload.summary;
  const setups = report.payload.setups;

  return {
    diagnostics: {
      excluded: Object.entries(summary.excludedCounts).map(([label, count]) => ({
        count,
        label: humanize(label),
      })),
      warnings: uniqueWarnings([
        ...report.payload.warnings,
        ...summary.warnings,
        ...setups.flatMap((setup) => setup.warnings),
      ]),
    },
    equityCurve: buildEquityCurve(report),
    metrics: [
      {
        id: "winRate",
        label: "Win rate",
        value: formatRatio(summary.winRate),
        detail: `${summary.tradeWinCount} wins / ${summary.tradeLossCount} losses`,
        tone: toneForWinRate(summary.winRate),
      },
      {
        id: "totalReturn",
        label: "Total return",
        value: formatPercent(summary.totalReturnPct),
        detail: `${formatCurrency(summary.averageNetPnl)} average net P&L`,
        tone: toneForSignedValue(summary.totalReturnPct),
      },
      {
        id: "maxDrawdown",
        label: "Max drawdown",
        value: formatPercent(summary.maxDrawdownPct, 2),
        detail: `${summary.metricsStatus.replace("_", " ")} metrics`,
        tone:
          summary.maxDrawdownPct === null
            ? "muted"
            : summary.maxDrawdownPct > 10
              ? "danger"
              : "warning",
      },
      {
        id: "sharpe",
        label: "Sharpe",
        value: formatDecimal(summary.sharpeRatio),
        detail: `${summary.benchmarkStatus.replace("_", " ")} benchmark`,
        tone: summary.sharpeRatio === null ? "muted" : "success",
      },
      {
        id: "beatsBuyHold",
        label: "Vs buy-and-hold",
        value: formatPercent(summary.excessReturnPct),
        detail:
          summary.beatsBuyAndHold === null
            ? "Benchmark unavailable"
            : summary.beatsBuyAndHold
              ? "Beat benchmark"
              : "Lagged benchmark",
        tone:
          summary.beatsBuyAndHold === null
            ? "muted"
            : summary.beatsBuyAndHold
              ? "success"
              : "danger",
      },
    ],
    metadata: {
      createdAt: report.createdAt,
      reportDate: report.reportDate,
      runId: report.payload.runId,
      target: report.target ?? "All targets",
      theme: report.theme ?? "All themes",
    },
    outcomeDistribution: [
      { label: "Win", count: summary.tradeWinCount },
      { label: "Loss", count: summary.tradeLossCount },
      { label: "Flat", count: summary.tradeFlatCount },
      { label: "Not evaluable", count: summary.tradeNotEvaluableCount },
    ],
    returnComparison: [
      { label: "Strategy", value: summary.totalReturnPct ?? 0 },
      { label: "Buy and hold", value: summary.buyHoldTotalReturnPct ?? 0 },
      { label: "Excess", value: summary.excessReturnPct ?? 0 },
    ],
    setupRows: setups.map(setupToRow),
  };
}

function buildEquityCurve(report: BacktestLearningReport): EquityCurvePoint[] {
  const startingEquity = report.payload.request?.startingEquity ?? 10_000;
  let strategyEquity = startingEquity;
  let buyHoldEquity = startingEquity;
  const points: EquityCurvePoint[] = [
    {
      buyHoldEquity,
      date: report.payload.request?.startDate ?? report.reportDate,
      label: "Start",
      strategyEquity,
    },
  ];

  const sorted = [...report.payload.setups].sort((a, b) =>
    a.exitDate.localeCompare(b.exitDate),
  );

  for (const setup of sorted) {
    strategyEquity += setup.tradePnl?.netPnl ?? 0;
    buyHoldEquity += benchmarkPnl(setup) ?? 0;
    points.push({
      buyHoldEquity: roundMoney(buyHoldEquity),
      date: setup.exitDate,
      label: setup.target,
      strategyEquity: roundMoney(strategyEquity),
    });
  }

  return points;
}

function setupToRow(setup: BacktestSetup): SetupRow {
  return {
    benchmarkReturn: formatPercent(benchmarkReturnPct(setup), 2),
    entryDate: setup.entryDate,
    exitDate: setup.exitDate,
    expression: setup.expression.replace("_", " "),
    netPnl: formatCurrency(setup.tradePnl?.netPnl ?? null),
    outcome: setup.tradePnl?.outcome ? humanize(setup.tradePnl.outcome) : UNAVAILABLE,
    setupId: setup.setupId,
    status: humanize(setup.strategyStatus),
    target: setup.target,
    theme: setup.theme ?? "Unknown",
    warningCount: setup.warnings.length,
  };
}

function benchmarkPnl(setup: BacktestSetup): number | null {
  const returnPct = benchmarkReturnPct(setup);
  if (returnPct === null) {
    return null;
  }
  return setup.allocatedCapital * (returnPct / 100);
}

function benchmarkReturnPct(setup: BacktestSetup): number | null {
  if (
    setup.underlyingEntryPrice === null ||
    setup.underlyingExitPrice === null ||
    setup.underlyingEntryPrice === 0
  ) {
    return null;
  }
  return (
    ((setup.underlyingExitPrice - setup.underlyingEntryPrice) /
      setup.underlyingEntryPrice) *
    100
  );
}

function formatCurrency(value: number | null): string {
  if (value === null) {
    return UNAVAILABLE;
  }
  return new Intl.NumberFormat("en-US", {
    currency: "USD",
    maximumFractionDigits: 2,
    minimumFractionDigits: 2,
    style: "currency",
  }).format(value);
}

function formatDecimal(value: number | null): string {
  if (value === null) {
    return UNAVAILABLE;
  }
  return value.toFixed(2);
}

function formatPercent(value: number | null, digits = 2): string {
  if (value === null) {
    return UNAVAILABLE;
  }
  return `${value.toFixed(digits)}%`;
}

function formatRatio(value: number | null): string {
  if (value === null) {
    return UNAVAILABLE;
  }
  return `${(value * 100).toFixed(1)}%`;
}

function humanize(value: string): string {
  return value.replaceAll("_", " ").toLowerCase();
}

function roundMoney(value: number): number {
  return Math.round(value * 100) / 100;
}

function toneForSignedValue(value: number | null): MetricTone {
  if (value === null) {
    return "muted";
  }
  if (value > 0) {
    return "success";
  }
  if (value < 0) {
    return "danger";
  }
  return "warning";
}

function toneForWinRate(value: number | null): MetricTone {
  if (value === null) {
    return "muted";
  }
  if (value >= 0.55) {
    return "success";
  }
  if (value >= 0.45) {
    return "warning";
  }
  return "danger";
}

function uniqueWarnings(warnings: string[]): string[] {
  return [...new Set(warnings.filter(Boolean))];
}
