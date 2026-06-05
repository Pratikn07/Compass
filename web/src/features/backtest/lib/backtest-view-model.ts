import type {
  BacktestLearningReport,
  BacktestSetup,
} from "@/features/backtest/lib/backtest-report.schema";

export type MetricTone = "danger" | "muted" | "success" | "warning";

export type BacktestMetric = {
  comparison: string;
  detail: string;
  id:
    | "maxDrawdown"
    | "sharpe"
    | "tradeCount"
    | "totalReturn"
    | "winRate";
  label: string;
  sparkline: number[];
  tone: MetricTone;
  value: string;
  verification: string;
};

export type BacktestDisplayMode = "dollars" | "percent";

export type EquityCurvePoint = {
  buyHoldEquity: number;
  buyHoldReturnPct: number;
  date: string;
  label: string;
  strategyEquity: number;
  strategyReturnPct: number;
};

export type DrawdownCurvePoint = {
  date: string;
  drawdownDollars: number;
  drawdownPct: number;
  label: string;
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
  holdingDays: number;
  netPnl: string;
  netPnlDollarLabel: string;
  netPnlPercentLabel: string;
  netPnlValue: number | null;
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
  console: {
    benchmarkStatus: string;
    dataQuality: { label: string; value: string }[];
    dateRange: string;
    evaluationHorizon: string;
    excludedTotal: string;
    includeRejectedCandidates: string;
    includeTradePnl: string;
    metricsStatus: string;
    runScope: { label: string; value: string }[];
    startingEquity: string;
    strategyType: string;
    tableControls: { label: string; value: string }[];
  };
  drawdownCurve: DrawdownCurvePoint[];
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
  const equityCurve = buildEquityCurve(report);
  const drawdownCurve = buildDrawdownCurve(equityCurve);
  const sparkline = equityCurve.map((point) => point.strategyReturnPct);
  const warnings = uniqueWarnings([
    ...report.payload.warnings,
    ...summary.warnings,
    ...setups.flatMap((setup) => setup.warnings),
  ]);
  const excludedTotal = String(
    Object.values(summary.excludedCounts).reduce((total, count) => total + count, 0),
  );
  const dateRange = formatDateRange(report);
  const evaluationHorizon = formatDays(
    report.payload.request?.evaluationHorizonDays,
  );
  const startingEquity = formatCurrency(
    report.payload.request?.startingEquity ?? null,
  );
  const strategyType = humanize(
    report.payload.request?.strategyType ?? "unknown_strategy",
  );
  const maxDrawdownDollars = Math.max(
    0,
    ...drawdownCurve.map((point) => point.drawdownDollars),
  );

  return {
    console: {
      benchmarkStatus: summary.benchmarkStatus,
      dataQuality: [
        { label: "Benchmark status", value: summary.benchmarkStatus },
        { label: "Metrics status", value: summary.metricsStatus },
        { label: "Excluded observations", value: excludedTotal },
        { label: "Warnings", value: String(warnings.length) },
      ],
      dateRange,
      evaluationHorizon,
      excludedTotal,
      includeRejectedCandidates: formatBoolean(
        report.payload.request?.includeRejectedCandidates,
      ),
      includeTradePnl: formatBoolean(report.payload.request?.includeTradePnl),
      metricsStatus: summary.metricsStatus,
      runScope: [
        { label: "Date range", value: dateRange },
        { label: "Theme", value: report.theme ?? "All themes" },
        { label: "Strategy", value: strategyType },
        { label: "Evaluation horizon", value: evaluationHorizon },
        { label: "Starting equity", value: startingEquity },
      ],
      startingEquity,
      strategyType,
      tableControls: [
        {
          label: "Sorting",
          value: "Target, theme, dates, holding days, realized P&L",
        },
        { label: "Pagination", value: "5, 10, 25, 50 rows per page" },
        { label: "Export", value: "CSV from parsed report rows" },
      ],
    },
    diagnostics: {
      excluded: Object.entries(summary.excludedCounts).map(([label, count]) => ({
        count,
        label: humanize(label),
      })),
      warnings,
    },
    metrics: [
      {
        comparison: `${summary.tradeWinCount}W / ${summary.tradeLossCount}L / ${summary.tradeFlatCount}F`,
        id: "winRate",
        label: "Win rate",
        value: formatRatio(summary.winRate),
        detail: `${summary.tradeWinCount} wins / ${summary.tradeLossCount} losses`,
        sparkline,
        tone: toneForWinRate(summary.winRate),
        verification: `${summary.tradeWinCount + summary.tradeLossCount + summary.tradeFlatCount} evaluable trades`,
      },
      {
        comparison: `Buy-and-hold ${formatPercent(summary.buyHoldTotalReturnPct)}`,
        id: "totalReturn",
        label: "Total return",
        value: formatPercent(summary.totalReturnPct),
        detail: `${formatPercent(summary.excessReturnPct)} vs benchmark`,
        sparkline,
        tone: toneForSignedValue(summary.totalReturnPct),
        verification: `Excess ${formatPercent(summary.excessReturnPct)}`,
      },
      {
        comparison: `Verified drawdown ${formatCurrency(maxDrawdownDollars)}`,
        id: "maxDrawdown",
        label: "Max drawdown",
        value: formatPercent(summary.maxDrawdownPct, 2),
        detail: `${summary.metricsStatus.replace("_", " ")} metrics`,
        sparkline,
        tone:
          summary.maxDrawdownPct === null
            ? "muted"
            : summary.maxDrawdownPct > 10
              ? "danger"
              : "warning",
        verification: `${drawdownCurve.length} equity points`,
      },
      {
        comparison: `${summary.benchmarkStatus.replace("_", " ")} benchmark`,
        id: "sharpe",
        label: "Sharpe",
        value: formatDecimal(summary.sharpeRatio),
        detail: `${summary.benchmarkStatus.replace("_", " ")} benchmark`,
        sparkline,
        tone: summary.sharpeRatio === null ? "muted" : "success",
        verification: `Risk-free ${formatPercent(report.payload.request?.annualRiskFreeRate ?? null)}`,
      },
      {
        comparison: `${summary.candidateReadyCount} candidate ready`,
        id: "tradeCount",
        label: "Trades",
        value: String(
          summary.tradeWinCount + summary.tradeLossCount + summary.tradeFlatCount,
        ),
        detail: `${summary.totalSetups} setups evaluated`,
        sparkline,
        tone: summary.totalSetups > 0 ? "success" : "muted",
        verification: `${summary.rejectedCount} rejected / ${summary.notEvaluableCount} not evaluable`,
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
    drawdownCurve,
    equityCurve,
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
      buyHoldReturnPct: 0,
      date: report.payload.request?.startDate ?? report.reportDate,
      label: "Start",
      strategyEquity,
      strategyReturnPct: 0,
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
      buyHoldReturnPct: roundPercent(
        percentChange(buyHoldEquity, startingEquity),
      ),
      date: setup.exitDate,
      label: setup.target,
      strategyEquity: roundMoney(strategyEquity),
      strategyReturnPct: roundPercent(
        percentChange(strategyEquity, startingEquity),
      ),
    });
  }

  return points;
}

function setupToRow(setup: BacktestSetup): SetupRow {
  const netPnlValue = setup.tradePnl?.netPnl ?? null;
  const netPnlDollarLabel = formatCurrency(netPnlValue);
  const netPnlPercentLabel = formatPercent(
    setup.tradePnl?.returnOnRiskPct ?? null,
    2,
  );

  return {
    benchmarkReturn: formatPercent(benchmarkReturnPct(setup), 2),
    entryDate: setup.entryDate,
    exitDate: setup.exitDate,
    expression: setup.expression.replace("_", " "),
    holdingDays: dateDiffDays(setup.entryDate, setup.exitDate),
    netPnl: netPnlDollarLabel,
    netPnlDollarLabel,
    netPnlPercentLabel,
    netPnlValue,
    outcome: setup.tradePnl?.outcome ? humanize(setup.tradePnl.outcome) : UNAVAILABLE,
    setupId: setup.setupId,
    status: humanize(setup.strategyStatus),
    target: setup.target,
    theme: setup.theme ?? "Unknown",
    warningCount: setup.warnings.length,
  };
}

function buildDrawdownCurve(points: EquityCurvePoint[]): DrawdownCurvePoint[] {
  let peak = points[0]?.strategyEquity ?? 0;

  return points.map((point) => {
    peak = Math.max(peak, point.strategyEquity);
    const drawdownDollars = roundMoney(Math.max(peak - point.strategyEquity, 0));

    return {
      date: point.date,
      drawdownDollars,
      drawdownPct: roundPercent(peak === 0 ? 0 : (drawdownDollars / peak) * 100),
      label: point.label,
    };
  });
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

function formatBoolean(value: boolean | null | undefined): string {
  if (value == null) {
    return UNAVAILABLE;
  }
  return value ? "Yes" : "No";
}

function formatDateRange(report: BacktestLearningReport): string {
  const request = report.payload.request;
  if (!request) {
    return report.reportDate;
  }
  return `${request.startDate} - ${request.endDate}`;
}

function formatDays(value: number | null | undefined): string {
  if (value == null) {
    return UNAVAILABLE;
  }
  return `${value} ${value === 1 ? "day" : "days"}`;
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

function roundPercent(value: number): number {
  return Math.round(value * 10_000) / 10_000;
}

function percentChange(value: number, basis: number): number {
  if (basis === 0) {
    return 0;
  }
  return ((value - basis) / basis) * 100;
}

function dateDiffDays(startDate: string, endDate: string): number {
  const start = Date.parse(`${startDate}T00:00:00Z`);
  const end = Date.parse(`${endDate}T00:00:00Z`);
  if (!Number.isFinite(start) || !Number.isFinite(end)) {
    return 0;
  }
  return Math.max(0, Math.round((end - start) / 86_400_000));
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
