import { z } from "zod";

export const BACKTEST_REPORT_TYPE = "backtest";

const nullableNumberSchema = z.number().nullable();
const optionalNullableStringSchema = z.string().nullable().optional();
const metricsStatusSchema = z.enum(["evaluable", "not_evaluable"]);
const tradeOutcomeSchema = z.enum(["win", "loss", "flat", "not_evaluable"]);
const tradeExpressionSchema = z.enum(["STOCK", "CALL_OPTION"]);

const requestSchema = z
  .object({
    run_id: z.string(),
    start_date: z.string(),
    end_date: z.string(),
    max_events: z.number().int().nullable(),
    strategy_type: z.string(),
    evaluation_horizon_days: z.number(),
    include_rejected_candidates: z.boolean(),
    include_trade_pnl: z.boolean(),
    positive_followthrough_threshold_pct: z.number(),
    negative_followthrough_threshold_pct: z.number(),
    starting_equity: z.number(),
    annual_risk_free_rate: z.number(),
  })
  .transform((value) => ({
    runId: value.run_id,
    startDate: value.start_date,
    endDate: value.end_date,
    maxEvents: value.max_events,
    strategyType: value.strategy_type,
    evaluationHorizonDays: value.evaluation_horizon_days,
    includeRejectedCandidates: value.include_rejected_candidates,
    includeTradePnl: value.include_trade_pnl,
    positiveFollowthroughThresholdPct: value.positive_followthrough_threshold_pct,
    negativeFollowthroughThresholdPct: value.negative_followthrough_threshold_pct,
    startingEquity: value.starting_equity,
    annualRiskFreeRate: value.annual_risk_free_rate,
  }));

const tradePnlSchema = z
  .object({
    ticker: z.string(),
    expression: tradeExpressionSchema,
    quantity: z.number(),
    entry_price: nullableNumberSchema,
    exit_price: nullableNumberSchema,
    gross_pnl: nullableNumberSchema,
    fees: z.number(),
    net_pnl: nullableNumberSchema,
    return_on_risk_pct: nullableNumberSchema,
    outcome: tradeOutcomeSchema,
    reason: optionalNullableStringSchema,
    not_evaluable_reason: optionalNullableStringSchema,
  })
  .transform((value) => ({
    ticker: value.ticker,
    expression: value.expression,
    quantity: value.quantity,
    entryPrice: value.entry_price,
    exitPrice: value.exit_price,
    grossPnl: value.gross_pnl,
    fees: value.fees,
    netPnl: value.net_pnl,
    returnOnRiskPct: value.return_on_risk_pct,
    outcome: value.outcome,
    reason: value.reason ?? null,
    notEvaluableReason: value.not_evaluable_reason ?? null,
  }));

const setupSchema = z
  .object({
    setup_id: z.string(),
    target: z.string(),
    ticker: z.string(),
    theme: z.string().nullable(),
    earnings_date: z.string().nullable(),
    entry_date: z.string(),
    exit_date: z.string(),
    strategy_status: z.string(),
    recommended_expression: tradeExpressionSchema.nullable(),
    expression: tradeExpressionSchema,
    allocated_capital: z.number(),
    underlying_entry_price: nullableNumberSchema,
    underlying_exit_price: nullableNumberSchema,
    underlying_outcome: z.unknown().nullable(),
    trade_pnl: tradePnlSchema.nullable(),
    reported_peers: z.array(z.string()),
    rejection_reasons: z.array(z.string()),
    warnings: z.array(z.string()),
  })
  .transform((value) => ({
    setupId: value.setup_id,
    target: value.target,
    ticker: value.ticker,
    theme: value.theme,
    earningsDate: value.earnings_date,
    entryDate: value.entry_date,
    exitDate: value.exit_date,
    strategyStatus: value.strategy_status,
    recommendedExpression: value.recommended_expression,
    expression: value.expression,
    allocatedCapital: value.allocated_capital,
    underlyingEntryPrice: value.underlying_entry_price,
    underlyingExitPrice: value.underlying_exit_price,
    underlyingOutcome: value.underlying_outcome,
    tradePnl: value.trade_pnl,
    reportedPeers: value.reported_peers,
    rejectionReasons: value.rejection_reasons,
    warnings: value.warnings,
  }));

const summarySchema = z
  .object({
    total_setups: z.number(),
    candidate_ready_count: z.number(),
    rejected_count: z.number(),
    not_evaluable_count: z.number(),
    underlying_win_count: z.number(),
    underlying_loss_count: z.number(),
    underlying_flat_count: z.number(),
    underlying_not_evaluable_count: z.number(),
    trade_win_count: z.number(),
    trade_loss_count: z.number(),
    trade_flat_count: z.number(),
    trade_not_evaluable_count: z.number(),
    average_underlying_return_pct: nullableNumberSchema,
    median_underlying_return_pct: nullableNumberSchema,
    average_net_pnl: nullableNumberSchema,
    median_net_pnl: nullableNumberSchema,
    by_theme: z.record(z.string(), z.number()),
    by_ticker: z.record(z.string(), z.number()),
    by_expression: z.record(z.string(), z.number()),
    top_rejection_reasons: z.record(z.string(), z.number()),
    win_rate: nullableNumberSchema,
    max_drawdown_pct: nullableNumberSchema,
    sharpe_ratio: nullableNumberSchema,
    total_return_pct: nullableNumberSchema,
    buy_hold_total_return_pct: nullableNumberSchema,
    beats_buy_and_hold: z.boolean().nullable(),
    excess_return_pct: nullableNumberSchema,
    benchmark_status: metricsStatusSchema,
    metrics_status: metricsStatusSchema,
    excluded_counts: z.record(z.string(), z.number()),
    warnings: z.array(z.string()),
  })
  .transform((value) => ({
    totalSetups: value.total_setups,
    candidateReadyCount: value.candidate_ready_count,
    rejectedCount: value.rejected_count,
    notEvaluableCount: value.not_evaluable_count,
    underlyingWinCount: value.underlying_win_count,
    underlyingLossCount: value.underlying_loss_count,
    underlyingFlatCount: value.underlying_flat_count,
    underlyingNotEvaluableCount: value.underlying_not_evaluable_count,
    tradeWinCount: value.trade_win_count,
    tradeLossCount: value.trade_loss_count,
    tradeFlatCount: value.trade_flat_count,
    tradeNotEvaluableCount: value.trade_not_evaluable_count,
    averageUnderlyingReturnPct: value.average_underlying_return_pct,
    medianUnderlyingReturnPct: value.median_underlying_return_pct,
    averageNetPnl: value.average_net_pnl,
    medianNetPnl: value.median_net_pnl,
    byTheme: value.by_theme,
    byTicker: value.by_ticker,
    byExpression: value.by_expression,
    topRejectionReasons: value.top_rejection_reasons,
    winRate: value.win_rate,
    maxDrawdownPct: value.max_drawdown_pct,
    sharpeRatio: value.sharpe_ratio,
    totalReturnPct: value.total_return_pct,
    buyHoldTotalReturnPct: value.buy_hold_total_return_pct,
    beatsBuyAndHold: value.beats_buy_and_hold,
    excessReturnPct: value.excess_return_pct,
    benchmarkStatus: value.benchmark_status,
    metricsStatus: value.metrics_status,
    excludedCounts: value.excluded_counts,
    warnings: value.warnings,
  }));

const backtestPayloadSchema = z
  .object({
    run_id: z.string(),
    request: requestSchema.nullable(),
    setups: z.array(setupSchema),
    summary: summarySchema,
    warnings: z.array(z.string()),
  })
  .transform((value) => ({
    runId: value.run_id,
    request: value.request,
    setups: value.setups,
    summary: value.summary,
    warnings: value.warnings,
  }));

export const backtestLearningReportRowSchema = z
  .object({
    learning_report_id: z.string(),
    run_id: z.string().nullable(),
    report_date: z.string(),
    target: z.string().nullable(),
    theme: z.string().nullable(),
    report_type: z.literal(BACKTEST_REPORT_TYPE),
    payload: backtestPayloadSchema,
    schema_version: z.number(),
    created_at: z.string(),
  })
  .transform((value) => ({
    learningReportId: value.learning_report_id,
    runId: value.run_id,
    reportDate: value.report_date,
    target: value.target,
    theme: value.theme,
    reportType: value.report_type,
    payload: value.payload,
    schemaVersion: value.schema_version,
    createdAt: value.created_at,
  }));

export type BacktestLearningReport = z.infer<
  typeof backtestLearningReportRowSchema
>;
export type BacktestPayload = BacktestLearningReport["payload"];
export type BacktestSetup = BacktestPayload["setups"][number];
