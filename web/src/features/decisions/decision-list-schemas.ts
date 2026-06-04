import { z } from "zod";

export const DecisionListPayloadSchema = z
  .object({
    thesis: z.string().optional(),
    decision_summary: z.string().optional(),
    outcome_type: z.string().optional(),
    candidate_brief: z
      .object({
        target: z.string().optional(),
        theme: z.string().nullable().optional(),
        main_thesis: z.string().optional(),
      })
      .passthrough()
      .optional(),
  })
  .passthrough();

export type DecisionListPayload = z.infer<typeof DecisionListPayloadSchema>;
